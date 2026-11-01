"""شهرت بازیکن — از رفتار بازی تأثیر می‌گیرد."""
from __future__ import annotations
from typing import Any

from core.database import db


async def _ensure(conn) -> None:
    await conn.execute(
        """CREATE TABLE IF NOT EXISTS player_reputation (
            telegram_id BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
            score INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )


async def add(user_id: int, delta: int) -> int:
    user_id = int(user_id)
    delta = int(delta)
    async with db().acquire() as conn:
        await _ensure(conn)
        await conn.execute(
            """INSERT INTO player_reputation(telegram_id, score, updated_at)
               VALUES($1,$2,NOW())
               ON CONFLICT(telegram_id)
               DO UPDATE SET score = GREATEST(-1000, LEAST(1000, player_reputation.score + EXCLUDED.score)),
                             updated_at=NOW()""",
            user_id,
            delta,
        )
        val = await conn.fetchval(
            "SELECT score FROM player_reputation WHERE telegram_id=$1", user_id
        )
    return int(val or 0)


async def get(user_id: int) -> dict[str, Any]:
    user_id = int(user_id)
    async with db().acquire() as conn:
        await _ensure(conn)
        val = await conn.fetchval(
            "SELECT score FROM player_reputation WHERE telegram_id=$1", user_id
        )
    score = int(val or 0)
    if score >= 200:
        label = "معتبر"
    elif score >= 50:
        label = "شناخته‌شده"
    elif score <= -200:
        label = "تحت تعقیب"
    elif score <= -50:
        label = "مشکوک"
    else:
        label = "عادی"
    return {"score": score, "label": label}
