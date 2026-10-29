from __future__ import annotations
from datetime import datetime, timezone
from games.empire.progression_rules import MISSIONS, ACHIEVEMENTS, mission_progress, level_for_xp
from core.database import db

async def _stats(conn, user_id: int) -> dict:
    row = await conn.fetchrow("""SELECT u.coins,u.games_played,u.wins,
      (SELECT COUNT(*) FROM empire_cities c WHERE c.owner_id=u.telegram_id) AS cities_owned,
      COALESCE((SELECT soldiers FROM empire_armies a WHERE a.telegram_id=u.telegram_id),0) AS soldiers,
      COALESCE(u.xp,0) AS xp
      FROM users u WHERE u.telegram_id=$1""", user_id)
    if not row: raise ValueError("کاربر پیدا نشد")
    return {k:int(row[k] or 0) for k in ("coins","games_played","wins","cities_owned","soldiers","xp")}

async def dashboard(user_id: int) -> dict:
    now = datetime.now(timezone.utc)
    day_key = now.strftime("%Y-%m-%d")
    iso = now.isocalendar(); week_key = f"{iso.year}-W{iso.week:02d}"
    async with db().acquire() as conn:
        stats = await _stats(conn, user_id)
        claims = await conn.fetch("SELECT mission_key,period_key FROM empire_mission_claims WHERE telegram_id=$1 AND period_key = ANY($2::text[])", user_id, [day_key, week_key])
        claimed = {(r['mission_key'],r['period_key']) for r in claims}
        missions = {}
        for kind, key in (("daily",day_key),("weekly",week_key)):
            missions[kind] = []
            for item in MISSIONS[kind]:
                row = mission_progress(item, stats); row["claimed"] = (item["key"],key) in claimed; row["period_key"] = key
                missions[kind].append(row)
        ach_claims = await conn.fetch("SELECT achievement_key FROM empire_achievement_claims WHERE telegram_id=$1", user_id)
        claimed_ach = {r['achievement_key'] for r in ach_claims}
        achievements = []
        for item in ACHIEVEMENTS:
            row = mission_progress(item, stats); row["claimed"] = item["key"] in claimed_ach
            achievements.append(row)
        stats["level"] = level_for_xp(stats["xp"]); stats["xp_to_next"] = stats["level"]*100-stats["xp"]
        return {"stats":stats,"missions":missions,"achievements":achievements,"periods":{"daily":day_key,"weekly":week_key}}

async def claim_mission(user_id: int, mission_key: str, kind: str) -> dict:
    if kind not in MISSIONS: raise ValueError("نوع مأموریت نامعتبر است")
    mission = next((m for m in MISSIONS[kind] if m["key"] == mission_key), None)
    if not mission: raise ValueError("مأموریت پیدا نشد")
    now = datetime.now(timezone.utc); iso=now.isocalendar()
    period = now.strftime("%Y-%m-%d") if kind == "daily" else f"{iso.year}-W{iso.week:02d}"
    async with db().acquire() as conn:
        async with conn.transaction():
            stats = await _stats(conn,user_id)
            progress = mission_progress(mission,stats)
            if not progress["complete"]: raise ValueError("هنوز شرط این مأموریت کامل نشده است")
            try:
                await conn.execute("INSERT INTO empire_mission_claims(telegram_id,mission_key,period_key) VALUES($1,$2,$3)",user_id,mission_key,period)
            except Exception as exc:
                if "unique" in str(exc).lower(): raise ValueError("پاداش این مأموریت را قبلاً در این دوره گرفته‌ای") from exc
                raise
            await conn.execute("UPDATE users SET coins=coins+$2,xp=COALESCE(xp,0)+$3 WHERE telegram_id=$1",user_id,mission["coins"],mission["xp"])
            await conn.execute("INSERT INTO empire_transactions(telegram_id,amount,reason) VALUES($1,$2,$3)",user_id,mission["coins"],f"mission:{mission_key}")
    return {"ok":True,"coins_reward":mission["coins"],"xp_reward":mission["xp"],"level":level_for_xp(stats["xp"]+mission["xp"])}

async def claim_achievement(user_id: int, achievement_key: str) -> dict:
    achievement = next((a for a in ACHIEVEMENTS if a["key"] == achievement_key), None)
    if not achievement: raise ValueError("دستاورد پیدا نشد")
    async with db().acquire() as conn:
        async with conn.transaction():
            stats=await _stats(conn,user_id)
            if not mission_progress(achievement,stats)["complete"]: raise ValueError("شرط این دستاورد هنوز کامل نشده است")
            try:
                await conn.execute("INSERT INTO empire_achievement_claims(telegram_id,achievement_key) VALUES($1,$2)",user_id,achievement_key)
            except Exception as exc:
                if "unique" in str(exc).lower(): raise ValueError("پاداش این دستاورد را قبلاً گرفته‌ای") from exc
                raise
            await conn.execute("UPDATE users SET coins=coins+$2,xp=COALESCE(xp,0)+$3 WHERE telegram_id=$1",user_id,achievement["coins"],achievement["xp"])
            await conn.execute("INSERT INTO empire_transactions(telegram_id,amount,reason) VALUES($1,$2,$3)",user_id,achievement["coins"],f"achievement:{achievement_key}")
    return {"ok":True,"coins_reward":achievement["coins"],"xp_reward":achievement["xp"],"level":level_for_xp(stats["xp"]+achievement["xp"])}
