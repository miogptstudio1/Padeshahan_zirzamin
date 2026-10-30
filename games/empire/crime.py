"""حمله به بازیکن، پناهگاه شروع، و فعالیت‌های خلاف."""
from __future__ import annotations
import random
from datetime import datetime, timezone, timedelta
from typing import Any

from core.database import db
from games.empire import service as empire_service
from games.empire.equipment import dashboard as equipment_dashboard
from games.empire.engine import army_power_bonus
from games.events import service as event_service

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
            """INSERT INTO player_hideouts(telegram_id, name, level, defense)
               VALUES($1,'پناهگاه کوچک',1,5)
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
    """برای کاربر جدید: پناهگاه + سرباز کم."""
    await ensure_hideout(user_id)


async def _power(user_id: int) -> int:
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

    return {
        "won": won,
        "stolen": max(0, stolen) if won else 0,
        "fee": abs(min(0, stolen)) if not won else 0,
        "attacker_power": atk_pow,
        "defender_power": def_pow,
        "defender_name": def_user["display_name"] if def_user else str(defender_id),
        "balance": int(bal_atk),
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
