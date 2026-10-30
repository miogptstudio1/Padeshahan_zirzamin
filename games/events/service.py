"""سیستم رویدادهای زمان‌دار با امتیاز، رتبه‌بندی و جایزه خودکار."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any

from core.database import db

# preset events that auto-rotate weekly
PRESETS = [
    {
        "event_key": "blood_week",
        "title": "🩸 هفته خونین",
        "description": "با جنگ قلمرو و پیروزی در بازی‌ها امتیاز بگیر. جایزه برای ۳ نفر برتر.",
        "kind": "weekly",
        "reward_coins": 2500,
        "reward_xp": 200,
        "metric": "combat",
        "days": 7,
    },
    {
        "event_key": "gold_caravan",
        "title": "🐪 کاروان طلایی",
        "description": "با کار روزانه، پاداش و جمع‌آوری درآمد امتیاز بگیر.",
        "kind": "weekly",
        "reward_coins": 1800,
        "reward_xp": 150,
        "metric": "economy",
        "days": 7,
    },
    {
        "event_key": "shadow_king",
        "title": "👑 پادشاه سایه‌ها",
        "description": "بیشترین سکهٔ به‌دست‌آمده در بازه ایونت.",
        "kind": "weekly",
        "reward_coins": 3000,
        "reward_xp": 250,
        "metric": "wealth",
        "days": 7,
    },
    {
        "event_key": "daily_hunt",
        "title": "🎯 شکار روزانه",
        "description": "ایونت ۲۴ ساعته — هر اقدام اقتصادی/رزمی امتیاز می‌دهد.",
        "kind": "daily",
        "reward_coins": 400,
        "reward_xp": 50,
        "metric": "points",
        "days": 1,
    },
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_active_events() -> None:
    """اگر ایونت فعالی نبود، یکی از presetها را زمان‌بندی کن."""
    async with db().acquire() as conn:
        active = await conn.fetchval(
            """SELECT COUNT(*) FROM game_events
               WHERE status='active' AND starts_at <= NOW() AND ends_at > NOW()"""
        )
        if active and int(active) > 0:
            # close expired
            await conn.execute(
                """UPDATE game_events SET status='ended'
                   WHERE status IN ('active','scheduled') AND ends_at <= NOW()"""
            )
            return
        await conn.execute(
            """UPDATE game_events SET status='ended'
               WHERE status IN ('active','scheduled') AND ends_at <= NOW()"""
        )
        # pick rotating preset by week number
        week = _now().isocalendar()[1]
        preset = PRESETS[week % len(PRESETS)]
        key = f"{preset['event_key']}_{_now().strftime('%Y%m%d')}"
        exists = await conn.fetchval("SELECT 1 FROM game_events WHERE event_key=$1", key)
        if exists:
            await conn.execute(
                """UPDATE game_events SET status='active'
                   WHERE event_key=$1 AND starts_at <= NOW() AND ends_at > NOW()""",
                key,
            )
            return
        starts = _now()
        ends = starts + timedelta(days=int(preset["days"]))
        await conn.execute(
            """INSERT INTO game_events(event_key,title,description,kind,starts_at,ends_at,
                  reward_coins,reward_xp,metric,status)
               VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,'active')
               ON CONFLICT(event_key) DO NOTHING""",
            key,
            preset["title"],
            preset["description"],
            preset["kind"],
            starts,
            ends,
            preset["reward_coins"],
            preset["reward_xp"],
            preset["metric"],
        )


async def list_events(limit: int = 5) -> list[dict[str, Any]]:
    await ensure_active_events()
    async with db().acquire() as conn:
        rows = await conn.fetch(
            """SELECT id,event_key,title,description,kind,starts_at,ends_at,
                      reward_coins,reward_xp,metric,status
               FROM game_events ORDER BY starts_at DESC LIMIT $1""",
            limit,
        )
    return [dict(r) for r in rows]


async def active_event() -> dict[str, Any] | None:
    await ensure_active_events()
    async with db().acquire() as conn:
        row = await conn.fetchrow(
            """SELECT * FROM game_events
               WHERE status='active' AND starts_at <= NOW() AND ends_at > NOW()
               ORDER BY ends_at ASC LIMIT 1"""
        )
    return dict(row) if row else None


async def add_score(user_id: int, points: int, metric: str | None = None) -> None:
    """امتیاز به ایونت فعال اضافه کن (metric اختیاری برای فیلتر)."""
    if points <= 0:
        return
    ev = await active_event()
    if not ev:
        return
    if metric and ev.get("metric") not in {metric, "points"}:
        # still allow generic points on combat/economy events loosely
        if metric not in {ev.get("metric"), "points"}:
            return
    async with db().acquire() as conn:
        await conn.execute(
            """INSERT INTO game_event_scores(event_id, telegram_id, points, updated_at)
               VALUES($1,$2,$3,NOW())
               ON CONFLICT(event_id, telegram_id) DO UPDATE
               SET points = game_event_scores.points + EXCLUDED.points, updated_at=NOW()""",
            int(ev["id"]),
            int(user_id),
            int(points),
        )


async def leaderboard(event_id: int | None = None, limit: int = 10) -> list[dict[str, Any]]:
    if event_id is None:
        ev = await active_event()
        if not ev:
            return []
        event_id = int(ev["id"])
    async with db().acquire() as conn:
        rows = await conn.fetch(
            """SELECT s.telegram_id, s.points, COALESCE(u.display_name, u.username, '') AS name
               FROM game_event_scores s
               LEFT JOIN users u ON u.telegram_id = s.telegram_id
               WHERE s.event_id=$1
               ORDER BY s.points DESC, s.updated_at ASC
               LIMIT $2""",
            int(event_id),
            limit,
        )
    return [
        {"rank": i, "telegram_id": int(r["telegram_id"]), "points": int(r["points"]), "name": r["name"]}
        for i, r in enumerate(rows, 1)
    ]


async def my_score(user_id: int) -> dict[str, Any] | None:
    ev = await active_event()
    if not ev:
        return None
    async with db().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT points FROM game_event_scores WHERE event_id=$1 AND telegram_id=$2",
            int(ev["id"]),
            int(user_id),
        )
        rank_row = await conn.fetchval(
            """SELECT 1 + COUNT(*) FROM game_event_scores
               WHERE event_id=$1 AND points > COALESCE($2,0)""",
            int(ev["id"]),
            int(row["points"]) if row else 0,
        )
    return {
        "event": ev,
        "points": int(row["points"]) if row else 0,
        "rank": int(rank_row) if row else None,
    }


async def settle_ended_events() -> list[dict[str, Any]]:
    """جایزه ۳ نفر اول ایونت‌های تمام‌شدهٔ پرداخت‌نشده."""
    paid: list[dict[str, Any]] = []
    async with db().acquire() as conn:
        ended = await conn.fetch(
            """SELECT * FROM game_events
               WHERE ends_at <= NOW() AND status IN ('active','ended','scheduled')
               ORDER BY ends_at DESC LIMIT 20"""
        )
        for ev in ended:
            await conn.execute("UPDATE game_events SET status='ended' WHERE id=$1", ev["id"])
            top = await conn.fetch(
                """SELECT telegram_id, points FROM game_event_scores
                   WHERE event_id=$1 ORDER BY points DESC, updated_at ASC LIMIT 3""",
                ev["id"],
            )
            rewards = [
                int(ev["reward_coins"]),
                max(0, int(ev["reward_coins"]) // 2),
                max(0, int(ev["reward_coins"]) // 4),
            ]
            for rank, row in enumerate(top, 1):
                claimed = await conn.fetchval(
                    "SELECT 1 FROM game_event_claims WHERE event_id=$1 AND telegram_id=$2",
                    ev["id"],
                    row["telegram_id"],
                )
                if claimed:
                    continue
                coins = rewards[rank - 1]
                await conn.execute(
                    "UPDATE users SET coins = coins + $2 WHERE telegram_id=$1",
                    row["telegram_id"],
                    coins,
                )
                await conn.execute(
                    """INSERT INTO game_event_claims(event_id, telegram_id, rank, reward_coins)
                       VALUES($1,$2,$3,$4)""",
                    ev["id"],
                    row["telegram_id"],
                    rank,
                    coins,
                )
                paid.append(
                    {
                        "event_id": int(ev["id"]),
                        "title": ev["title"],
                        "telegram_id": int(row["telegram_id"]),
                        "rank": rank,
                        "coins": coins,
                    }
                )
    return paid
