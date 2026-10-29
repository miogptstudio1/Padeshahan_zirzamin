"""Persistent alliance notifications with per-category Telegram delivery preferences (v0.28)."""
from __future__ import annotations
from core.database import db

from games.empire.alliance_notification_rules import CATEGORIES, validate_preferences

async def notify_alliance_members(bot, alliance_id: int, category: str, title: str, message: str,
                                  actor_id: int | None = None, exclude_actor: bool = False) -> int:
    if category not in CATEGORIES:
        category = "general"
    async with db().acquire() as conn:
        members = await conn.fetch("""SELECT m.telegram_id,COALESCE(s.telegram_enabled,TRUE) AS telegram_enabled,
            COALESCE(p.enabled,TRUE) AS category_enabled
            FROM empire_alliance_members m LEFT JOIN empire_alliance_notification_preferences p
              ON p.telegram_id=m.telegram_id AND p.category=$2
            LEFT JOIN empire_alliance_notification_settings s ON s.telegram_id=m.telegram_id
            WHERE m.alliance_id=$1""", alliance_id, category)
        await conn.execute("""INSERT INTO empire_alliance_history(alliance_id,event_type,title,description,actor_id)
            VALUES($1,$2,$3,$4,$5)""", alliance_id, category, title[:120], message[:1000], actor_id)
        recipients = [int(r["telegram_id"]) for r in members
                      if bool(r["category_enabled"]) and not (exclude_actor and actor_id == int(r["telegram_id"]))]
        if not recipients:
            return 0
        await conn.executemany("""INSERT INTO empire_alliance_notifications
            (alliance_id,telegram_id,category,title,message,actor_id)
            VALUES($1,$2,$3,$4,$5,$6)""",
            [(alliance_id, uid, category, title[:120], message[:1000], actor_id) for uid in recipients])
    prefs = {int(r["telegram_id"]): bool(r["telegram_enabled"]) and bool(r["category_enabled"]) for r in members}
    sent = 0
    for uid in recipients:
        if not prefs.get(uid, True):
            continue
        try:
            await bot.send_message(uid, f"🔔 {title}\n{message}")
            sent += 1
        except Exception:
            # Persistent in-app inbox still stores the event if Telegram DMs are unavailable.
            pass
    return sent

async def list_notifications(user_id: int, limit: int = 30):
    async with db().acquire() as conn:
        rows = await conn.fetch("""SELECT id,category,title,message,is_read,created_at FROM empire_alliance_notifications
            WHERE telegram_id=$1 ORDER BY id DESC LIMIT $2""", user_id, min(max(int(limit), 1), 100))
        return [dict(r) for r in rows]

async def mark_read(user_id: int, notification_id: int | None = None):
    async with db().acquire() as conn:
        if notification_id is None:
            result = await conn.execute("UPDATE empire_alliance_notifications SET is_read=TRUE WHERE telegram_id=$1 AND is_read=FALSE", user_id)
        else:
            result = await conn.execute("UPDATE empire_alliance_notifications SET is_read=TRUE WHERE telegram_id=$1 AND id=$2", user_id, notification_id)
        return int(result.rsplit(" ", 1)[-1])

async def get_preferences(user_id: int):
    async with db().acquire() as conn:
        rows = await conn.fetch("SELECT category,enabled FROM empire_alliance_notification_preferences WHERE telegram_id=$1", user_id)
        telegram_enabled = await conn.fetchval("SELECT telegram_enabled FROM empire_alliance_notification_settings WHERE telegram_id=$1", user_id)
        values = {r["category"]: bool(r["enabled"]) for r in rows}
        return {"telegram_enabled": True if telegram_enabled is None else bool(telegram_enabled),
                "categories": {k: values.get(k, True) for k in CATEGORIES}, "category_names": CATEGORIES}

async def update_preferences(user_id: int, telegram_enabled: bool, categories: dict[str, bool]):
    validated = validate_preferences(telegram_enabled, categories)
    telegram_enabled = validated["telegram_enabled"]
    categories = validated["categories"]
    async with db().acquire() as conn:
        await conn.execute("""INSERT INTO empire_alliance_notification_settings(telegram_id,telegram_enabled)
            VALUES($1,$2) ON CONFLICT(telegram_id) DO UPDATE SET telegram_enabled=EXCLUDED.telegram_enabled,updated_at=NOW()""", user_id, telegram_enabled)
        for category, enabled in categories.items():
            await conn.execute("""INSERT INTO empire_alliance_notification_preferences(telegram_id,category,enabled)
                VALUES($1,$2,$3) ON CONFLICT(telegram_id,category) DO UPDATE SET enabled=EXCLUDED.enabled,updated_at=NOW()""", user_id, category, enabled)
    return await get_preferences(user_id)

async def notify_user_alliance(bot, user_id: int, category: str, title: str, message: str,
                               exclude_actor: bool = False) -> int:
    async with db().acquire() as conn:
        alliance_id = await conn.fetchval("SELECT alliance_id FROM empire_alliance_members WHERE telegram_id=$1", user_id)
    if not alliance_id:
        return 0
    return await notify_alliance_members(bot, int(alliance_id), category, title, message,
                                         actor_id=user_id, exclude_actor=exclude_actor)
