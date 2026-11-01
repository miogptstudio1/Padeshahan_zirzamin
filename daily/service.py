"""مأموریت روزانه ساده — یک بار در روز."""
from __future__ import annotations
from datetime import datetime, timezone, date
from typing import Any

from core.database import db

# kind -> (title, target, reward_coins)
MISSIONS = {
    "work": ("یک بار کار کن", 1, 40),
    "daily": ("پاداش روزانه بگیر", 1, 30),
    "attack": ("یک حمله موفق", 1, 60),
    "boss": ("یک ضربه به باس", 1, 50),
}


async def _ensure_table(conn) -> None:
    await conn.execute(
        """CREATE TABLE IF NOT EXISTS daily_mission_progress (
            telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
            day DATE NOT NULL,
            kind TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            claimed BOOLEAN NOT NULL DEFAULT FALSE,
            PRIMARY KEY (telegram_id, day, kind)
        )"""
    )


def _today() -> date:
    return datetime.now(timezone.utc).date()


async def progress(user_id: int, kind: str, amount: int = 1) -> None:
    if kind not in MISSIONS:
        return
    user_id = int(user_id)
    day = _today()
    async with db().acquire() as conn:
        await _ensure_table(conn)
        await conn.execute(
            """INSERT INTO daily_mission_progress(telegram_id, day, kind, progress)
               VALUES($1,$2,$3,$4)
               ON CONFLICT(telegram_id, day, kind)
               DO UPDATE SET progress = daily_mission_progress.progress + EXCLUDED.progress""",
            user_id,
            day,
            kind,
            int(amount),
        )


async def status(user_id: int) -> list[dict[str, Any]]:
    user_id = int(user_id)
    day = _today()
    async with db().acquire() as conn:
        await _ensure_table(conn)
        rows = await conn.fetch(
            """SELECT kind, progress, claimed FROM daily_mission_progress
               WHERE telegram_id=$1 AND day=$2""",
            user_id,
            day,
        )
    by = {r["kind"]: r for r in rows}
    out = []
    for kind, (title, target, reward) in MISSIONS.items():
        r = by.get(kind)
        prog = int(r["progress"]) if r else 0
        claimed = bool(r["claimed"]) if r else False
        out.append({
            "kind": kind,
            "title": title,
            "progress": min(prog, target),
            "target": target,
            "reward": reward,
            "done": prog >= target,
            "claimed": claimed,
        })
    return out


async def claim_all(user_id: int) -> dict[str, Any]:
    user_id = int(user_id)
    day = _today()
    total = 0
    claimed_kinds = []
    async with db().acquire() as conn:
        await _ensure_table(conn)
        async with conn.transaction():
            for kind, (title, target, reward) in MISSIONS.items():
                row = await conn.fetchrow(
                    """SELECT progress, claimed FROM daily_mission_progress
                       WHERE telegram_id=$1 AND day=$2 AND kind=$3 FOR UPDATE""",
                    user_id,
                    day,
                    kind,
                )
                if not row or int(row["progress"]) < target or row["claimed"]:
                    continue
                await conn.execute(
                    """UPDATE daily_mission_progress SET claimed=TRUE
                       WHERE telegram_id=$1 AND day=$2 AND kind=$3""",
                    user_id,
                    day,
                    kind,
                )
                total += reward
                claimed_kinds.append(kind)
            if total:
                await conn.execute(
                    "UPDATE users SET coins = coins + $2 WHERE telegram_id=$1",
                    user_id,
                    total,
                )
            bal = await conn.fetchval(
                "SELECT coins FROM users WHERE telegram_id=$1", user_id
            )
    return {"reward": total, "kinds": claimed_kinds, "balance": int(bal or 0)}
