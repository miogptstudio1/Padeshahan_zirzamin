"""زورخانه — ارتقای قدرت، سرعت، سلامتی، استقامت."""
from __future__ import annotations
from typing import Any

from core.database import db

# سقف سطح هر مهارت
MAX_STAT = 50

STATS = {
    "strength": {
        "label": "قدرت",
        "emoji": "💪",
        "desc": "دمیج حمله و باس",
    },
    "speed": {
        "label": "سرعت",
        "emoji": "⚡",
        "desc": "شانس ضربه و خلاف",
    },
    "vitality": {
        "label": "سلامتی",
        "emoji": "❤️",
        "desc": "حداکثر جان",
    },
    "stamina": {
        "label": "استقامت",
        "emoji": "🛡️",
        "desc": "دفاع و مقاومت",
    },
}


def train_cost(level: int) -> int:
    """هزینه ارتقا از level به level+1."""
    lv = max(0, int(level))
    return 80 + lv * 45 + (lv * lv) // 2


async def _ensure(conn) -> None:
    await conn.execute(
        """CREATE TABLE IF NOT EXISTS player_gym_stats (
            telegram_id BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
            strength INTEGER NOT NULL DEFAULT 0 CHECK (strength >= 0 AND strength <= 50),
            speed INTEGER NOT NULL DEFAULT 0 CHECK (speed >= 0 AND speed <= 50),
            vitality INTEGER NOT NULL DEFAULT 0 CHECK (vitality >= 0 AND vitality <= 50),
            stamina INTEGER NOT NULL DEFAULT 0 CHECK (stamina >= 0 AND stamina <= 50),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )


async def ensure_stats(user_id: int) -> dict[str, Any]:
    user_id = int(user_id)
    async with db().acquire() as conn:
        await _ensure(conn)
        row = await conn.fetchrow(
            "SELECT * FROM player_gym_stats WHERE telegram_id=$1", user_id
        )
        if not row:
            await conn.execute(
                "INSERT INTO player_gym_stats(telegram_id) VALUES($1) ON CONFLICT DO NOTHING",
                user_id,
            )
            row = await conn.fetchrow(
                "SELECT * FROM player_gym_stats WHERE telegram_id=$1", user_id
            )
    return dict(row) if row else {
        "telegram_id": user_id,
        "strength": 0,
        "speed": 0,
        "vitality": 0,
        "stamina": 0,
    }


async def train(user_id: int, stat: str) -> dict[str, Any]:
    user_id = int(user_id)
    stat = (stat or "").strip().lower()
    aliases = {
        "قدرت": "strength",
        "strength": "strength",
        "str": "strength",
        "سرعت": "speed",
        "speed": "speed",
        "سلامتی": "vitality",
        "vitality": "vitality",
        "hp": "vitality",
        "جان": "vitality",
        "استقامت": "stamina",
        "stamina": "stamina",
        "دفاع": "stamina",
    }
    key = aliases.get(stat)
    if not key or key not in STATS:
        raise ValueError("کدوم؟ قدرت · سرعت · سلامتی · استقامت")

    async with db().acquire() as conn:
        await _ensure(conn)
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM player_gym_stats WHERE telegram_id=$1 FOR UPDATE",
                user_id,
            )
            if not row:
                await conn.execute(
                    "INSERT INTO player_gym_stats(telegram_id) VALUES($1)", user_id
                )
                row = await conn.fetchrow(
                    "SELECT * FROM player_gym_stats WHERE telegram_id=$1 FOR UPDATE",
                    user_id,
                )
            cur = int(row[key] or 0)
            if cur >= MAX_STAT:
                raise ValueError(f"{STATS[key]['label']} به سقف رسید ({MAX_STAT}).")
            cost = train_cost(cur)
            coins = int(
                await conn.fetchval(
                    "SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE", user_id
                )
                or 0
            )
            if coins < cost:
                raise ValueError(f"سکه کم داری. لازم: {cost} · موجودی: {coins}")
            await conn.execute(
                "UPDATE users SET coins = coins - $2 WHERE telegram_id=$1",
                user_id,
                cost,
            )
            await conn.execute(
                f"UPDATE player_gym_stats SET {key}=$2, updated_at=NOW() WHERE telegram_id=$1",
                user_id,
                cur + 1,
            )
            # سلامتی → max_hp پناهگاه
            if key == "vitality":
                new_max = 100 + (cur + 1) * 8
                await conn.execute(
                    """UPDATE player_hideouts
                       SET max_hp=$2,
                           hp = LEAST(hp + 8, $2)
                       WHERE telegram_id=$1""",
                    user_id,
                    new_max,
                )
            bal = int(
                await conn.fetchval(
                    "SELECT coins FROM users WHERE telegram_id=$1", user_id
                )
                or 0
            )
    meta = STATS[key]
    return {
        "stat": key,
        "label": meta["label"],
        "emoji": meta["emoji"],
        "level": cur + 1,
        "cost": cost,
        "balance": bal,
        "next_cost": train_cost(cur + 1) if cur + 1 < MAX_STAT else None,
    }


async def combat_bonus(user_id: int) -> dict[str, int]:
    """بونوس عددی برای نبرد."""
    s = await ensure_stats(user_id)
    strength = int(s.get("strength") or 0)
    speed = int(s.get("speed") or 0)
    vitality = int(s.get("vitality") or 0)
    stamina = int(s.get("stamina") or 0)
    return {
        "strength": strength,
        "speed": speed,
        "vitality": vitality,
        "stamina": stamina,
        "attack": strength * 3 + speed,
        "defense": stamina * 3 + strength // 2,
        "max_hp_bonus": vitality * 8,
        "power": strength * 3 + speed * 2 + stamina * 2 + vitality,
    }


async def status_text(user_id: int) -> str:
    s = await ensure_stats(user_id)
    bonus = await combat_bonus(user_id)
    lines = ["🏋️ زورخانه\n"]
    for key, meta in STATS.items():
        lv = int(s.get(key) or 0)
        cost = train_cost(lv) if lv < MAX_STAT else "سقف"
        lines.append(
            f"{meta['emoji']} {meta['label']}: سطح {lv}/{MAX_STAT} "
            f"— ارتقا: {cost} سکه"
        )
        lines.append(f"   {meta['desc']}")
    lines.append(
        f"\n⚔️ بونوس حمله: +{bonus['attack']}\n"
        f"🛡️ بونوس دفاع: +{bonus['defense']}\n"
        f"❤️ بونوس جان: +{bonus['max_hp_bonus']}\n"
        f"💥 قدرت کلی: +{bonus['power']}"
    )
    lines.append("\nارتقا: تمرین قدرت · تمرین سرعت · تمرین سلامتی · تمرین استقامت")
    return "\n".join(lines)
