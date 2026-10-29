"""Alliance treasury-funded buildings and temporary defensive shields."""
from core.database import db

from games.empire.alliance_building_rules import BUILDINGS, MAX_LEVEL, SHIELD_COST, SHIELD_HOURS

async def overview(user_id: int):
    async with db().acquire() as conn:
        row = await conn.fetchrow("""SELECT a.id,a.name,a.leader_id,m.rank,COALESCE(t.balance,0)::bigint AS balance,
            COALESCE(b.fortress_level,0)::int AS fortress_level,COALESCE(b.academy_level,0)::int AS academy_level,
            b.shield_until FROM empire_alliance_members m JOIN empire_alliances a ON a.id=m.alliance_id
            LEFT JOIN empire_alliance_treasuries t ON t.alliance_id=a.id LEFT JOIN empire_alliance_buildings b ON b.alliance_id=a.id
            WHERE m.telegram_id=$1""", user_id)
        if not row: raise ValueError("برای مدیریت ساختمان‌ها باید عضو یک اتحاد باشی.")
        shield = row["shield_until"]
        return {"alliance_id": int(row["id"]), "alliance_name": row["name"], "is_leader": int(row["leader_id"]) == user_id, "can_manage_buildings": row["rank"] in ("leader", "commander"),
            "treasury_balance": int(row["balance"]), "fortress_level": int(row["fortress_level"]),
            "academy_level": int(row["academy_level"]), "shield_until": shield.isoformat() if shield else None,
            "shield_active": bool(shield and shield.timestamp() > __import__("time").time()),
            "buildings": {k: {"name":v["name"],"level":int(row[v["column"]]),"next_cost":v["base_cost"]*(int(row[v["column"]])+1),"effect":v["effect"]} for k,v in BUILDINGS.items()},
            "shield_cost": SHIELD_COST, "shield_hours": SHIELD_HOURS}

async def upgrade(user_id: int, building: str):
    if building not in BUILDINGS: raise ValueError("نوع ساختمان نامعتبر است.")
    spec=BUILDINGS[building]; col=spec["column"]
    async with db().acquire() as conn:
        async with conn.transaction():
            member=await conn.fetchrow("SELECT a.id,a.leader_id,m.rank FROM empire_alliance_members m JOIN empire_alliances a ON a.id=m.alliance_id WHERE m.telegram_id=$1 FOR UPDATE OF a,m",user_id)
            if not member: raise ValueError("عضو اتحاد نیستی.")
            if member["rank"] not in ("leader", "commander"): raise ValueError("فقط رهبر یا فرمانده می‌تواند ساختمان ارتقا دهد.")
            aid=int(member["id"]); await conn.execute("INSERT INTO empire_alliance_buildings(alliance_id) VALUES($1) ON CONFLICT DO NOTHING",aid)
            row=await conn.fetchrow(f"SELECT {col} AS level FROM empire_alliance_buildings WHERE alliance_id=$1 FOR UPDATE",aid)
            level=int(row["level"]);
            if level>=MAX_LEVEL: raise ValueError("این ساختمان به بالاترین سطح رسیده است.")
            cost=spec["base_cost"]*(level+1)
            treasury=await conn.fetchrow("SELECT balance FROM empire_alliance_treasuries WHERE alliance_id=$1 FOR UPDATE",aid)
            if not treasury or int(treasury["balance"])<cost: raise ValueError(f"برای ارتقا به {cost} سکه در خزانه نیاز است.")
            await conn.execute(f"UPDATE empire_alliance_buildings SET {col}={col}+1,updated_at=NOW() WHERE alliance_id=$1",aid)
            await conn.execute("UPDATE empire_alliance_treasuries SET balance=balance-$2,updated_at=NOW() WHERE alliance_id=$1",aid,cost)
            await conn.execute("INSERT INTO empire_alliance_treasury_transactions(alliance_id,actor_id,amount,reason) VALUES($1,$2,$3,$4)",aid,user_id,-cost,f"building:{building}:level:{level+1}")
            return {"ok":True,"building":building,"name":spec["name"],"level":level+1,"cost":cost,"effect":spec["effect"]}

async def activate_shield(user_id: int):
    async with db().acquire() as conn:
        async with conn.transaction():
            member=await conn.fetchrow("SELECT a.id,a.leader_id FROM empire_alliance_members m JOIN empire_alliances a ON a.id=m.alliance_id WHERE m.telegram_id=$1 FOR UPDATE OF a",user_id)
            if not member: raise ValueError("عضو اتحاد نیستی.")
            if int(member["leader_id"]) != user_id: raise ValueError("فقط رهبر اتحاد می‌تواند سپر دفاعی فعال کند.")
            aid=int(member["id"]); await conn.execute("INSERT INTO empire_alliance_buildings(alliance_id) VALUES($1) ON CONFLICT DO NOTHING",aid)
            row=await conn.fetchrow("SELECT shield_until FROM empire_alliance_buildings WHERE alliance_id=$1 FOR UPDATE",aid)
            active=await conn.fetchval("SELECT shield_until>NOW() FROM empire_alliance_buildings WHERE alliance_id=$1",aid)
            if active: raise ValueError("سپر دفاعی اتحاد هنوز فعال است.")
            t=await conn.fetchrow("SELECT balance FROM empire_alliance_treasuries WHERE alliance_id=$1 FOR UPDATE",aid)
            if not t or int(t["balance"])<SHIELD_COST: raise ValueError(f"برای فعال‌سازی سپر به {SHIELD_COST} سکه در خزانه نیاز است.")
            await conn.execute("UPDATE empire_alliance_treasuries SET balance=balance-$2,updated_at=NOW() WHERE alliance_id=$1",aid,SHIELD_COST)
            await conn.execute("UPDATE empire_alliance_buildings SET shield_until=NOW()+INTERVAL '6 hours',updated_at=NOW() WHERE alliance_id=$1",aid)
            await conn.execute("INSERT INTO empire_alliance_treasury_transactions(alliance_id,actor_id,amount,reason) VALUES($1,$2,$3,'defensive_shield')",aid,user_id,-SHIELD_COST)
            until=await conn.fetchval("SELECT shield_until FROM empire_alliance_buildings WHERE alliance_id=$1",aid)
            return {"ok":True,"cost":SHIELD_COST,"shield_until":until.isoformat(),"hours":SHIELD_HOURS}
