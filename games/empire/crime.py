"""حمله به بازیکن، پناهگاه شروع، و فعالیت‌های خلاف."""
from __future__ import annotations
import random
from datetime import datetime, timezone, timedelta
from typing import Any

from core.database import db
from games.empire import service as empire_service
from games.empire.equipment import dashboard as equipment_dashboard
from games.empire.engine import army_power_bonus
from games.empire import army_advanced
from games.events import service as event_service
from games.daily import service as daily_service
from games.reputation import service as rep_service

ATTACK_COOLDOWN = 15 * 60  # 15 min
CRIME_COOLDOWN = 5 * 60
STARTER_COINS = 50
STARTER_SOLDIERS = 3


async def ensure_hideout(user_id: int) -> dict[str, Any]:
    user_id = int(user_id)
    async with db().acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM player_hideouts WHERE telegram_id=$1", user_id)
        if row:
            return dict(row)
        await conn.execute(
            """INSERT INTO player_hideouts(telegram_id, name, level, defense, hp, max_hp)
               VALUES($1,'پناهگاه کوچک',1,5,100,100)
               ON CONFLICT(telegram_id) DO NOTHING""",
            user_id,
        )
        # starter army if none
        army = await conn.fetchrow("SELECT soldiers FROM empire_armies WHERE telegram_id=$1", user_id)
        if not army:
            await conn.execute(
                "INSERT INTO empire_armies(telegram_id,soldiers) VALUES($1,$2) ON CONFLICT DO NOTHING",
                user_id,
                STARTER_SOLDIERS,
            )
        row = await conn.fetchrow("SELECT * FROM player_hideouts WHERE telegram_id=$1", user_id)
    return dict(row) if row else {"telegram_id": user_id, "name": "پناهگاه کوچک", "level": 1, "defense": 5}


async def grant_starter_pack(user_id: int) -> None:
    """برای کاربر جدید: پناهگاه + سرباز + قلمرو اولیه رایگان."""
    await ensure_hideout(user_id)
    await _assign_starter_city(user_id)


async def _assign_starter_city(user_id: int) -> str | None:
    """یک outpost آزاد به بازیکن بده تا بتواند جنگ قلمرو راه بیندازد."""
    user_id = int(user_id)
    async with db().acquire() as conn:
        owned = await conn.fetchval(
            "SELECT city_key FROM empire_cities WHERE owner_id=$1 LIMIT 1", user_id
        )
        if owned:
            return owned
        free = await conn.fetchrow(
            """SELECT city_key, name FROM empire_cities
               WHERE owner_id IS NULL AND city_key LIKE 'outpost_%'
               ORDER BY city_key LIMIT 1 FOR UPDATE"""
        )
        if not free:
            # fallback: any free cheap city
            free = await conn.fetchrow(
                """SELECT city_key, name FROM empire_cities
                   WHERE owner_id IS NULL AND price=0
                   ORDER BY city_key LIMIT 1 FOR UPDATE"""
            )
        if not free:
            return None
        await conn.execute(
            "UPDATE empire_cities SET owner_id=$2, defense_level=1, updated_at=NOW() WHERE city_key=$1",
            free["city_key"],
            user_id,
        )
        return free["city_key"]


async def _power(user_id: int) -> int:
    try:
        adv = await army_advanced.total_army_power(user_id)
        base = int(adv.get("total") or 0)
    except Exception:
        army = await empire_service.army_for(user_id)
        soldiers = int(army.get("soldiers") or 0)
        base = army_power_bonus(soldiers) + soldiers
    try:
        eq = await equipment_dashboard(user_id)
        stats = eq.get("stats") or {}
        base += int(stats.get("attack") or 0) + int(stats.get("defense") or 0) // 2
    except Exception:
        pass
    hide = await ensure_hideout(user_id)
    base += int(hide.get("defense") or 0) + int(hide.get("level") or 1) * 2
    return max(1, base)


async def attack_player(attacker_id: int, defender_id: int) -> dict[str, Any]:
    attacker_id, defender_id = int(attacker_id), int(defender_id)
    if attacker_id == defender_id:
        raise ValueError("نمی‌تونی به خودت حمله کنی.")
    await ensure_hideout(attacker_id)
    await ensure_hideout(defender_id)

    async with db().acquire() as conn:
        async with conn.transaction():
            # cooldown
            last = await conn.fetchval(
                """SELECT created_at FROM pvp_attacks
                   WHERE attacker_id=$1 ORDER BY id DESC LIMIT 1""",
                attacker_id,
            )
            now = datetime.now(timezone.utc)
            if last:
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                elapsed = (now - last).total_seconds()
                if elapsed < ATTACK_COOLDOWN:
                    remain = int(ATTACK_COOLDOWN - elapsed)
                    raise ValueError(f"هنوز آماده‌ای نه! {max(1, remain // 60)} دقیقه دیگر دوباره حمله کن.")

            atk_user = await conn.fetchrow(
                "SELECT coins, is_banned FROM users WHERE telegram_id=$1 FOR UPDATE", attacker_id
            )
            def_user = await conn.fetchrow(
                "SELECT coins, is_banned, display_name FROM users WHERE telegram_id=$1 FOR UPDATE",
                defender_id,
            )
            if not atk_user:
                raise ValueError("اول «شروع» را بزن.")
            if not def_user:
                raise ValueError("بازیکن هدف پیدا نشد.")
            if def_user["is_banned"]:
                raise ValueError("هدف مسدود است.")

    # چک جان
    async with db().acquire() as conn:
        ahp = await conn.fetchval("SELECT hp FROM player_hideouts WHERE telegram_id=$1", attacker_id)
        dhp = await conn.fetchval("SELECT hp FROM player_hideouts WHERE telegram_id=$1", defender_id)
    if ahp is not None and int(ahp) <= 0:
        raise ValueError("جان تو تمام شده؛ اول «هیل» بزن.")
    if dhp is not None and int(dhp) <= 0:
        raise ValueError("هدف بی‌هوش است؛ فعلاً قابل حمله نیست.")

    atk_pow = await _power(attacker_id)
    def_pow = await _power(defender_id)
    # chance weighted by power
    ratio = atk_pow / (atk_pow + def_pow)
    roll = random.random()
    won = roll < (0.35 + ratio * 0.5)  # 35%..85%

    stolen = 0
    async with db().acquire() as conn:
        async with conn.transaction():
            def_user = await conn.fetchrow(
                "SELECT coins, display_name FROM users WHERE telegram_id=$1 FOR UPDATE", defender_id
            )
            atk_user = await conn.fetchrow(
                "SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE", attacker_id
            )
            def_coins = int(def_user["coins"])
            if won:
                # steal 5%–18% of target coins, min 1 max 2000
                pct = 0.05 + random.random() * 0.13
                stolen = int(def_coins * pct)
                stolen = max(0, min(2000, stolen))
                if stolen > 0:
                    await conn.execute(
                        "UPDATE users SET coins = coins - $2 WHERE telegram_id=$1",
                        defender_id,
                        stolen,
                    )
                    await conn.execute(
                        "UPDATE users SET coins = coins + $2 WHERE telegram_id=$1",
                        attacker_id,
                        stolen,
                    )
            else:
                # fail: lose small fee
                fee = min(50, int(atk_user["coins"]))
                if fee > 0:
                    await conn.execute(
                        "UPDATE users SET coins = coins - $2 WHERE telegram_id=$1",
                        attacker_id,
                        fee,
                    )
                    stolen = -fee
            # آسیب جانی
            hp_damage = 0
            def_hp_left = 100
            if won:
                hp_damage = max(8, min(40, 10 + (atk_pow - def_pow) // 5 + random.randint(0, 10)))
                drow = await conn.fetchrow(
                    "SELECT hp, max_hp FROM player_hideouts WHERE telegram_id=$1 FOR UPDATE",
                    defender_id,
                )
                if drow:
                    cur_hp = int(drow["hp"] or 100)
                    def_hp_left = max(0, cur_hp - hp_damage)
                    await conn.execute(
                        "UPDATE player_hideouts SET hp=$2 WHERE telegram_id=$1",
                        defender_id,
                        def_hp_left,
                    )
            else:
                # مهاجم زخمی جزئی
                fee_hp = random.randint(3, 12)
                arow = await conn.fetchrow(
                    "SELECT hp FROM player_hideouts WHERE telegram_id=$1 FOR UPDATE",
                    attacker_id,
                )
                if arow:
                    await conn.execute(
                        "UPDATE player_hideouts SET hp=$2 WHERE telegram_id=$1",
                        attacker_id,
                        max(1, int(arow["hp"] or 100) - fee_hp),
                    )
                hp_damage = fee_hp
            await conn.execute(
                """INSERT INTO pvp_attacks(attacker_id,defender_id,stolen,attacker_power,defender_power,won)
                   VALUES($1,$2,$3,$4,$5,$6)""",
                attacker_id,
                defender_id,
                max(0, stolen) if won else 0,
                atk_pow,
                def_pow,
                won,
            )
            await conn.execute(
                "UPDATE player_hideouts SET last_attacked_at=NOW() WHERE telegram_id=$1",
                defender_id,
            )
            bal_atk = await conn.fetchval("SELECT coins FROM users WHERE telegram_id=$1", attacker_id)

    try:
        await event_service.add_score(attacker_id, 15 if won else 5, "combat")
    except Exception:
        pass
    if won:
        try:
            await daily_service.progress(attacker_id, "attack", 1)
        except Exception:
            pass
        try:
            await rep_service.add(attacker_id, -3)
        except Exception:
            pass

    return {
        "won": won,
        "stolen": max(0, stolen) if won else 0,
        "fee": abs(min(0, stolen)) if not won else 0,
        "attacker_power": atk_pow,
        "defender_power": def_pow,
        "defender_name": def_user["display_name"] if def_user else str(defender_id),
        "balance": int(bal_atk),
        "hp_damage": hp_damage,
        "defender_hp": def_hp_left if won else None,
    }


async def pickpocket(actor_id: int, target_id: int) -> dict[str, Any]:
    """جیب‌بری — ریسک کمتر، سود کمتر."""
    actor_id, target_id = int(actor_id), int(target_id)
    if actor_id == target_id:
        raise ValueError("خودت را نمی‌تونی بزنی.")
    await _crime_cooldown(actor_id)
    async with db().acquire() as conn:
        async with conn.transaction():
            t = await conn.fetchrow(
                "SELECT coins, display_name FROM users WHERE telegram_id=$1 FOR UPDATE", target_id
            )
            a = await conn.fetchrow(
                "SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE", actor_id
            )
            if not t or not a:
                raise ValueError("بازیکن پیدا نشد.")
            success = random.random() < 0.55
            amount = 0
            if success:
                amount = max(1, min(120, int(int(t["coins"]) * 0.03) + random.randint(5, 25)))
                amount = min(amount, int(t["coins"]))
                await conn.execute(
                    "UPDATE users SET coins=coins-$2 WHERE telegram_id=$1", target_id, amount
                )
                await conn.execute(
                    "UPDATE users SET coins=coins+$2 WHERE telegram_id=$1", actor_id, amount
                )
            else:
                fine = min(30, int(a["coins"]))
                if fine:
                    await conn.execute(
                        "UPDATE users SET coins=coins-$2 WHERE telegram_id=$1", actor_id, fine
                    )
                amount = -fine
            await conn.execute(
                """INSERT INTO crime_logs(actor_id,target_id,kind,amount,success,detail)
                   VALUES($1,$2,'pickpocket',$3,$4,$5)""",
                actor_id,
                target_id,
                abs(amount),
                success,
                "",
            )
            await conn.execute(
                "UPDATE player_hideouts SET last_crime_at=NOW() WHERE telegram_id=$1", actor_id
            )
            bal = await conn.fetchval("SELECT coins FROM users WHERE telegram_id=$1", actor_id)
    try:
        await event_service.add_score(actor_id, 8 if success else 2, "combat")
    except Exception:
        pass
    return {
        "success": success,
        "amount": abs(amount) if success else 0,
        "fine": abs(amount) if not success else 0,
        "target_name": t["display_name"],
        "balance": int(bal),
    }


async def smuggle(actor_id: int) -> dict[str, Any]:
    """قاچاق — بدون هدف؛ شانس سود یا جریمه."""
    actor_id = int(actor_id)
    await _crime_cooldown(actor_id)
    async with db().acquire() as conn:
        async with conn.transaction():
            a = await conn.fetchrow(
                "SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE", actor_id
            )
            if not a:
                raise ValueError("اول شروع را بزن.")
            success = random.random() < 0.6
            if success:
                amount = random.randint(40, 180)
                await conn.execute(
                    "UPDATE users SET coins=coins+$2 WHERE telegram_id=$1", actor_id, amount
                )
            else:
                amount = min(80, int(a["coins"]))
                await conn.execute(
                    "UPDATE users SET coins=coins-$2 WHERE telegram_id=$1", actor_id, amount
                )
                amount = -amount
            await conn.execute(
                """INSERT INTO crime_logs(actor_id,target_id,kind,amount,success)
                   VALUES($1,NULL,'smuggle',$2,$3)""",
                actor_id,
                abs(amount),
                success,
            )
            await conn.execute(
                "UPDATE player_hideouts SET last_crime_at=NOW() WHERE telegram_id=$1", actor_id
            )
            bal = await conn.fetchval("SELECT coins FROM users WHERE telegram_id=$1", actor_id)
    try:
        await event_service.add_score(actor_id, 6 if success else 1, "combat")
    except Exception:
        pass
    return {"success": success, "amount": amount, "balance": int(bal)}


async def extort(actor_id: int, target_id: int) -> dict[str, Any]:
    """باج‌گیری — نیاز به قدرت بالاتر."""
    actor_id, target_id = int(actor_id), int(target_id)
    if actor_id == target_id:
        raise ValueError("باج از خودت؟")
    await _crime_cooldown(actor_id)
    ap, dp = await _power(actor_id), await _power(target_id)
    if ap < dp:
        raise ValueError("قدرتت از هدف کمتر است؛ باج‌گیری شکست می‌خورد. اول ارتش/سلاح قوی‌تر کن.")
    async with db().acquire() as conn:
        async with conn.transaction():
            t = await conn.fetchrow(
                "SELECT coins, display_name FROM users WHERE telegram_id=$1 FOR UPDATE", target_id
            )
            if not t:
                raise ValueError("هدف پیدا نشد.")
            amount = max(10, min(300, int(int(t["coins"]) * 0.04)))
            amount = min(amount, int(t["coins"]))
            success = random.random() < 0.7
            if success and amount:
                await conn.execute(
                    "UPDATE users SET coins=coins-$2 WHERE telegram_id=$1", target_id, amount
                )
                await conn.execute(
                    "UPDATE users SET coins=coins+$2 WHERE telegram_id=$1", actor_id, amount
                )
            else:
                amount = 0
                success = False
            await conn.execute(
                """INSERT INTO crime_logs(actor_id,target_id,kind,amount,success)
                   VALUES($1,$2,'extort',$3,$4)""",
                actor_id,
                target_id,
                amount,
                success,
            )
            await conn.execute(
                "UPDATE player_hideouts SET last_crime_at=NOW() WHERE telegram_id=$1", actor_id
            )
            bal = await conn.fetchval("SELECT coins FROM users WHERE telegram_id=$1", actor_id)
    return {
        "success": success,
        "amount": amount,
        "target_name": t["display_name"],
        "balance": int(bal),
    }


async def upgrade_hideout(user_id: int) -> dict[str, Any]:
    user_id = int(user_id)
    h = await ensure_hideout(user_id)
    level = int(h["level"])
    if level >= 20:
        raise ValueError("پناهگاه در حداکثر سطح است.")
    cost = 100 * level
    async with db().acquire() as conn:
        async with conn.transaction():
            coins = await conn.fetchval(
                "SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE", user_id
            )
            if int(coins) < cost:
                raise ValueError(f"هزینه ارتقا {cost} سکه است.")
            await conn.execute(
                "UPDATE users SET coins=coins-$2 WHERE telegram_id=$1", user_id, cost
            )
            await conn.execute(
                """UPDATE player_hideouts
                   SET level=level+1, defense=defense+3, name=CASE
                     WHEN level+1>=10 THEN 'دژ زیرزمینی'
                     WHEN level+1>=5 THEN 'پناهگاه مستحکم'
                     ELSE name END
                   WHERE telegram_id=$1""",
                user_id,
            )
            row = await conn.fetchrow(
                "SELECT * FROM player_hideouts WHERE telegram_id=$1", user_id
            )
            bal = await conn.fetchval("SELECT coins FROM users WHERE telegram_id=$1", user_id)
    return {"hideout": dict(row), "cost": cost, "balance": int(bal)}


async def _crime_cooldown(user_id: int) -> None:
    async with db().acquire() as conn:
        last = await conn.fetchval(
            "SELECT last_crime_at FROM player_hideouts WHERE telegram_id=$1", int(user_id)
        )
    if not last:
        await ensure_hideout(user_id)
        return
    now = datetime.now(timezone.utc)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    elapsed = (now - last).total_seconds()
    if elapsed < CRIME_COOLDOWN:
        raise ValueError(f"برای جرم بعدی {max(1, int(CRIME_COOLDOWN-elapsed)//60)} دقیقه صبر کن.")


async def hideout_status(user_id: int) -> dict[str, Any]:
    h = await ensure_hideout(user_id)
    power = await _power(user_id)
    return {"hideout": h, "power": power}

HEAL_COOLDOWN = 10 * 60  # 10 minutes
HEAL_AMOUNT = 35


async def heal_self(user_id: int) -> dict:
    user_id = int(user_id)
    await ensure_hideout(user_id)
    async with db().acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT hp, max_hp, last_heal_at FROM player_hideouts WHERE telegram_id=$1 FOR UPDATE",
                user_id,
            )
            if not row:
                raise ValueError("پناهگاه پیدا نشد.")
            now = datetime.now(timezone.utc)
            last = row["last_heal_at"]
            if last is not None:
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                elapsed = (now - last).total_seconds()
                if elapsed < HEAL_COOLDOWN:
                    raise ValueError(f"هیل هنوز آماده نیست؛ {max(1, int(HEAL_COOLDOWN-elapsed)//60)} دقیقه صبر کن.")
            hp = int(row["hp"] or 100)
            max_hp = int(row["max_hp"] or 100)
            if hp >= max_hp:
                raise ValueError("جان تو کامل است.")
            new_hp = min(max_hp, hp + HEAL_AMOUNT)
            await conn.execute(
                "UPDATE player_hideouts SET hp=$2, last_heal_at=NOW() WHERE telegram_id=$1",
                user_id,
                new_hp,
            )
    return {"hp": new_hp, "max_hp": max_hp, "healed": new_hp - hp}


async def hp_status(user_id: int) -> dict:
    h = await ensure_hideout(user_id)
    return {
        "hp": int(h.get("hp") or 100),
        "max_hp": int(h.get("max_hp") or 100),
        "name": h.get("name"),
        "level": h.get("level"),
        "defense": h.get("defense"),
        "power": await _power(user_id),
    }

