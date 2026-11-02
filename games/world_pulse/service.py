"""ایونت‌های ساعتی جهان + باف موقت (دمیج، دفاع، سکه)."""
from __future__ import annotations
import random
from datetime import datetime, timezone, timedelta
from typing import Any

from core.database import db

# kind -> effect applied in combat/economy
PULSE_EVENTS = [
    {
        "key": "gunfire",
        "title": "صدای شلیک",
        "message": "صدای شلیک شنیده شد… جنگ شدت گرفت. آسیب بازیکن‌ها ۳۰٪ بیشتر شده.",
        "buff": "damage",
        "mult": 1.30,
        "minutes": 45,
    },
    {
        "key": "blood_moon",
        "title": "ماه خونین",
        "message": "ماه خونین طلوع کرد. ضربه‌ها وحشی‌تر شدن (+۲۵٪ دمیج).",
        "buff": "damage",
        "mult": 1.25,
        "minutes": 40,
    },
    {
        "key": "fog_cover",
        "title": "مه غلیظ",
        "message": "مه اومد رو شهر. دفاع‌ها قوی‌ترن (+۲۰٪ دفاع).",
        "buff": "defense",
        "mult": 1.20,
        "minutes": 35,
    },
    {
        "key": "gold_rush",
        "title": "تب طلا",
        "message": "کاروان طلایی رد شد. درآمد کار و پاداش ۲۰٪ بیشتره.",
        "buff": "economy",
        "mult": 1.20,
        "minutes": 50,
    },
    {
        "key": "quiet_street",
        "title": "خیابان خلوت",
        "message": "شهر آروم شده. خلاف‌کاری‌ها کم‌ریسک‌ترن (شانس موفقیت بهتر).",
        "buff": "crime_luck",
        "mult": 1.15,
        "minutes": 30,
    },
    {
        "key": "sirens",
        "title": "آژیر پلیس",
        "message": "آژیر کشیده شد. آسیب بازیکن‌ها ۱۰٪ کمتره؛ احتیاط کنید.",
        "buff": "damage",
        "mult": 0.90,
        "minutes": 25,
    },
    {
        "key": "boss_roar",
        "title": "غرش از اعماق",
        "message": "چیزی از زیرزمین غرش کرد… باس‌ها آسیب‌پذیرتر شدن (+۳۵٪ دمیج به باس).",
        "buff": "boss_damage",
        "mult": 1.35,
        "minutes": 40,
    },
    {
        "key": "blackout",
        "title": "قطع برق",
        "message": "شهر تاریک شد. جاسوسی راحت‌تره و خلاف داغ‌تر.",
        "buff": "crime_luck",
        "mult": 1.25,
        "minutes": 30,
    },
]


async def _ensure_tables(conn) -> None:
    await conn.execute(
        """CREATE TABLE IF NOT EXISTS world_pulses (
            id BIGSERIAL PRIMARY KEY,
            pulse_key TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            buff TEXT NOT NULL,
            mult DOUBLE PRECISION NOT NULL DEFAULT 1.0,
            starts_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ends_at TIMESTAMPTZ NOT NULL,
            announced BOOLEAN NOT NULL DEFAULT FALSE
        )"""
    )
    await conn.execute(
        """CREATE TABLE IF NOT EXISTS group_bosses (
            id BIGSERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            boss_key TEXT NOT NULL,
            name TEXT NOT NULL,
            max_hp BIGINT NOT NULL,
            hp BIGINT NOT NULL,
            reward_pool INTEGER NOT NULL DEFAULT 2000,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ends_at TIMESTAMPTZ,
            defeated_at TIMESTAMPTZ
        )"""
    )
    await conn.execute(
        """CREATE TABLE IF NOT EXISTS group_boss_damage (
            boss_id BIGINT NOT NULL REFERENCES group_bosses(id) ON DELETE CASCADE,
            telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
            damage BIGINT NOT NULL DEFAULT 0,
            hits INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (boss_id, telegram_id)
        )"""
    )
    await conn.execute(
        """CREATE INDEX IF NOT EXISTS group_bosses_chat_active
           ON group_bosses(chat_id) WHERE status='active'"""
    )


async def active_buffs() -> list[dict[str, Any]]:
    async with db().acquire() as conn:
        await _ensure_tables(conn)
        rows = await conn.fetch(
            """SELECT * FROM world_pulses
               WHERE ends_at > NOW()
               ORDER BY ends_at DESC"""
        )
    return [dict(r) for r in rows]


async def buff_multiplier(kind: str) -> float:
    """ضرب‌کننده فعال برای damage / defense / economy / crime_luck / boss_damage."""
    mult = 1.0
    for b in await active_buffs():
        if b.get("buff") == kind:
            mult *= float(b.get("mult") or 1.0)
    return mult


async def maybe_spawn_hourly_pulse() -> dict[str, Any] | None:
    """اگر ایونت ساعتی فعال نیست، یکی رندوم بساز."""
    async with db().acquire() as conn:
        await _ensure_tables(conn)
        live = await conn.fetchval(
            "SELECT COUNT(*) FROM world_pulses WHERE ends_at > NOW()"
        )
        if int(live or 0) > 0:
            return None
        # حداکثر یکی هر ~۵۰–۷۰ دقیقه از آخرین
        last = await conn.fetchval(
            "SELECT ends_at FROM world_pulses ORDER BY id DESC LIMIT 1"
        )
        now = datetime.now(timezone.utc)
        if last is not None:
            if getattr(last, "tzinfo", None) is None:
                last = last.replace(tzinfo=timezone.utc)
            if (now - last).total_seconds() < 20 * 60:
                return None
        preset = random.choice(PULSE_EVENTS)
        ends = now + timedelta(minutes=int(preset["minutes"]))
        rid = await conn.fetchval(
            """INSERT INTO world_pulses(pulse_key, title, message, buff, mult, ends_at)
               VALUES($1,$2,$3,$4,$5,$6) RETURNING id""",
            preset["key"],
            preset["title"],
            preset["message"],
            preset["buff"],
            float(preset["mult"]),
            ends,
        )
        row = await conn.fetchrow("SELECT * FROM world_pulses WHERE id=$1", rid)
    return dict(row) if row else None


async def force_pulse(key: str | None = None) -> dict[str, Any]:
    """اجبار ایونت (ادمین یا تست)."""
    preset = None
    if key:
        for p in PULSE_EVENTS:
            if p["key"] == key or p["title"] == key:
                preset = p
                break
    if not preset:
        preset = random.choice(PULSE_EVENTS)
    now = datetime.now(timezone.utc)
    ends = now + timedelta(minutes=int(preset["minutes"]))
    async with db().acquire() as conn:
        await _ensure_tables(conn)
        # بستن قبلی‌ها
        await conn.execute("UPDATE world_pulses SET ends_at=NOW() WHERE ends_at > NOW()")
        rid = await conn.fetchval(
            """INSERT INTO world_pulses(pulse_key, title, message, buff, mult, ends_at)
               VALUES($1,$2,$3,$4,$5,$6) RETURNING id""",
            preset["key"],
            preset["title"],
            preset["message"],
            preset["buff"],
            float(preset["mult"]),
            ends,
        )
        row = await conn.fetchrow("SELECT * FROM world_pulses WHERE id=$1", rid)
    return dict(row)


async def status_text() -> str:
    buffs = await active_buffs()
    if not buffs:
        return "الان ایونت ساعتی فعالی نیست. هر از گاهی یکی می‌آد."
    lines = ["ایونت‌های فعال جهان:\n"]
    now = datetime.now(timezone.utc)
    for b in buffs:
        ends = b["ends_at"]
        if ends and getattr(ends, "tzinfo", None) is None:
            ends = ends.replace(tzinfo=timezone.utc)
        left = max(1, int((ends - now).total_seconds() // 60)) if ends else "?"
        lines.append(f"• {b['title']}: {b['message']}")
        lines.append(f"  باقی‌مانده: حدود {left} دقیقه")
    return "\n".join(lines)


# ——— باس گروهی ———

GROUP_BOSS_PRESETS = [
    {"boss_key": "street_thug", "name": "اوباش خیابان", "max_hp": 25000, "reward_pool": 1500},
    {"boss_key": "smuggler_king", "name": "شاه قاچاق", "max_hp": 45000, "reward_pool": 2800},
    {"boss_key": "corrupt_captain", "name": "کاپیتان فاسد", "max_hp": 70000, "reward_pool": 4000},
    {"boss_key": "underground_beast", "name": "هیولای زیرزمین", "max_hp": 100000, "reward_pool": 5500},
]


async def ensure_group_boss(chat_id: int, force_new: bool = False) -> dict[str, Any]:
    chat_id = int(chat_id)
    async with db().acquire() as conn:
        await _ensure_tables(conn)
        if not force_new:
            row = await conn.fetchrow(
                """SELECT * FROM group_bosses
                   WHERE chat_id=$1 AND status='active'
                     AND (ends_at IS NULL OR ends_at > NOW())
                   ORDER BY id DESC LIMIT 1""",
                chat_id,
            )
            if row and int(row["hp"]) > 0:
                return dict(row)
            await conn.execute(
                """UPDATE group_bosses SET status='defeated'
                   WHERE chat_id=$1 AND status='active'""",
                chat_id,
            )
        preset = random.choice(GROUP_BOSS_PRESETS)
        ends = datetime.now(timezone.utc) + timedelta(hours=6)
        rid = await conn.fetchval(
            """INSERT INTO group_bosses(chat_id, boss_key, name, max_hp, hp, reward_pool, status, ends_at)
               VALUES($1,$2,$3,$4,$4,$5,'active',$6) RETURNING id""",
            chat_id,
            preset["boss_key"],
            preset["name"],
            preset["max_hp"],
            preset["reward_pool"],
            ends,
        )
        row = await conn.fetchrow("SELECT * FROM group_bosses WHERE id=$1", rid)
    return dict(row)


async def attack_group_boss(chat_id: int, user_id: int) -> dict[str, Any]:
    chat_id, user_id = int(chat_id), int(user_id)
    boss = await ensure_group_boss(chat_id, force_new=False)
    if int(boss["hp"]) <= 0 or boss["status"] != "active":
        boss = await ensure_group_boss(chat_id, force_new=True)

    try:
        power = await army_advanced.total_army_power(user_id)
        atk = max(6, int(power.get("total") or 15) // 4 + random.randint(2, 10))
    except Exception:
        atk = random.randint(15, 45)

    try:
        mult = await buff_multiplier("boss_damage")
        dmg_mult = await buff_multiplier("damage")
        atk = max(1, int(atk * mult * max(dmg_mult, 1.0)))
    except Exception:
        pass

    async with db().acquire() as conn:
        await _ensure_tables(conn)
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM group_bosses WHERE id=$1 FOR UPDATE", boss["id"]
            )
            if not row or row["status"] != "active" or int(row["hp"]) <= 0:
                raise ValueError("باس گروه تموم شده. دوباره «باس گروه» بزن.")
            new_hp = max(0, int(row["hp"]) - atk)
            await conn.execute(
                "UPDATE group_bosses SET hp=$2 WHERE id=$1", row["id"], new_hp
            )
            await conn.execute(
                """INSERT INTO group_boss_damage(boss_id, telegram_id, damage, hits)
                   VALUES($1,$2,$3,1)
                   ON CONFLICT(boss_id, telegram_id)
                   DO UPDATE SET damage = group_boss_damage.damage + EXCLUDED.damage,
                                 hits = group_boss_damage.hits + 1""",
                row["id"],
                user_id,
                atk,
            )
            defeated = new_hp <= 0
            rewards = []
            if defeated:
                await conn.execute(
                    """UPDATE group_bosses SET status='defeated', defeated_at=NOW()
                       WHERE id=$1""",
                    row["id"],
                )
                pool = int(row["reward_pool"])
                top = await conn.fetch(
                    """SELECT telegram_id, damage FROM group_boss_damage
                       WHERE boss_id=$1 ORDER BY damage DESC LIMIT 5""",
                    row["id"],
                )
                shares = [0.35, 0.25, 0.18, 0.12, 0.10]
                for i, r in enumerate(top):
                    pay = int(pool * shares[i]) if i < len(shares) else 0
                    if pay > 0:
                        await conn.execute(
                            "UPDATE users SET coins = coins + $2 WHERE telegram_id=$1",
                            r["telegram_id"],
                            pay,
                        )
                        rewards.append(
                            {
                                "telegram_id": int(r["telegram_id"]),
                                "coins": pay,
                                "rank": i + 1,
                            }
                        )
            my = await conn.fetchrow(
                """SELECT damage, hits FROM group_boss_damage
                   WHERE boss_id=$1 AND telegram_id=$2""",
                row["id"],
                user_id,
            )

    player_hp = None
    try:
        player_hp = await crime_service.damage_hp(user_id, max(8, random.randint(10, 28)))
    except Exception:
        player_hp = None
    try:
        await event_service.add_score(user_id, max(3, atk // 25), "combat")
    except Exception:
        pass

    return {
        "damage": atk,
        "boss_hp": new_hp,
        "boss_max": int(row["max_hp"]),
        "boss_name": row["name"],
        "defeated": defeated,
        "rewards": rewards,
        "my_damage": int(my["damage"]) if my else atk,
        "chat_id": chat_id,
        "player_hp": player_hp,
    }


# lazy imports at bottom to avoid cycles
from games.empire import army_advanced  # noqa: E402
from games.empire import crime as crime_service  # noqa: E402
from games.events import service as event_service  # noqa: E402
