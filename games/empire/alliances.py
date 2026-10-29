"""Persistent alliance system for the Underworld Kings empire game."""
from __future__ import annotations
from core.database import db
from games.empire.alliance_rules import clean_name, clean_tag


async def my_alliance(user_id: int):
    async with db().acquire() as conn:
        return await conn.fetchrow("""SELECT a.id,a.name,a.tag,a.leader_id,a.created_at,m.role,
            (SELECT COUNT(*) FROM empire_alliance_members x WHERE x.alliance_id=a.id) AS member_count
            FROM empire_alliance_members m JOIN empire_alliances a ON a.id=m.alliance_id
            WHERE m.telegram_id=$1""", user_id)


async def create_alliance(user_id: int, name: str, tag: str):
    name, tag = clean_name(name), clean_tag(tag)
    async with db().acquire() as conn:
        async with conn.transaction():
            existing = await conn.fetchval("SELECT 1 FROM empire_alliance_members WHERE telegram_id=$1", user_id)
            if existing:
                raise ValueError("قبل از ساخت اتحاد، باید از اتحاد فعلی خارج شوی.")
            try:
                row = await conn.fetchrow("""INSERT INTO empire_alliances(name,tag,leader_id)
                    VALUES($1,$2,$3) RETURNING id,name,tag,leader_id,created_at""", name, tag, user_id)
            except Exception as exc:
                if getattr(exc, "sqlstate", None) == "23505":
                    raise ValueError("این نام یا برچسب اتحاد قبلاً استفاده شده است.") from exc
                raise
            await conn.execute("INSERT INTO empire_alliance_members(alliance_id,telegram_id,role,rank) VALUES($1,$2,'leader','leader')", row["id"], user_id)
            await conn.execute("INSERT INTO empire_alliance_history(alliance_id,event_type,title,description,actor_id) VALUES($1,'alliance_created','اتحاد ساخته شد',$2,$3)", int(row["id"]), f"اتحاد «{name}» ایجاد شد.", user_id)
            return dict(row)


async def list_alliances(limit: int = 30, search: str = ""):
    search = search.strip()[:32]
    async with db().acquire() as conn:
        rows = await conn.fetch("""SELECT a.id,a.name,a.tag,a.leader_id,u.display_name AS leader_name,
            COUNT(m.telegram_id)::int AS member_count, COALESCE(SUM(COALESCE(c.city_count,0)),0)::int AS cities_owned
            FROM empire_alliances a JOIN users u ON u.telegram_id=a.leader_id
            LEFT JOIN empire_alliance_members m ON m.alliance_id=a.id
            LEFT JOIN (SELECT owner_id,COUNT(*)::int AS city_count FROM empire_cities WHERE owner_id IS NOT NULL GROUP BY owner_id) c ON c.owner_id=m.telegram_id
            WHERE ($1='' OR a.name ILIKE '%'||$1||'%' OR a.tag ILIKE '%'||$1||'%')
            GROUP BY a.id,u.display_name ORDER BY member_count DESC,cities_owned DESC,a.created_at ASC LIMIT $2""", search, limit)
        return [dict(r) for r in rows]


async def request_to_join(user_id: int, alliance_id: int):
    async with db().acquire() as conn:
        async with conn.transaction():
            if await conn.fetchval("SELECT 1 FROM empire_alliance_members WHERE telegram_id=$1", user_id):
                raise ValueError("برای پیوستن، ابتدا باید از اتحاد فعلی خارج شوی.")
            alliance = await conn.fetchrow("SELECT id,name FROM empire_alliances WHERE id=$1", alliance_id)
            if not alliance:
                raise ValueError("اتحاد پیدا نشد.")
            pending = await conn.fetchval("SELECT id FROM empire_alliance_requests WHERE alliance_id=$1 AND requester_id=$2 AND status='pending'", alliance_id, user_id)
            if pending:
                raise ValueError("درخواست پیوستن تو قبلاً ثبت شده و منتظر بررسی است.")
            request_id = await conn.fetchval("""INSERT INTO empire_alliance_requests(alliance_id,requester_id)
                VALUES($1,$2) RETURNING id""", alliance_id, user_id)
            return {"request_id": request_id, "alliance_name": alliance["name"]}


async def incoming_requests(leader_id: int):
    async with db().acquire() as conn:
        rows = await conn.fetch("""SELECT r.id,r.alliance_id,r.requester_id,r.created_at,a.name AS alliance_name,
            u.display_name AS requester_name,u.username AS requester_username
            FROM empire_alliance_requests r JOIN empire_alliances a ON a.id=r.alliance_id
            JOIN users u ON u.telegram_id=r.requester_id
            WHERE a.leader_id=$1 AND r.status='pending' ORDER BY r.created_at ASC LIMIT 50""", leader_id)
        return [dict(r) for r in rows]


async def manage_request(leader_id: int, request_id: int, accept: bool):
    async with db().acquire() as conn:
        async with conn.transaction():
            req = await conn.fetchrow("""SELECT r.id,r.alliance_id,r.requester_id,a.name FROM empire_alliance_requests r
                JOIN empire_alliances a ON a.id=r.alliance_id WHERE r.id=$1 AND a.leader_id=$2 AND r.status='pending' FOR UPDATE OF r""", request_id, leader_id)
            if not req:
                raise ValueError("درخواست پیدا نشد یا قبلاً بررسی شده است.")
            if accept:
                if await conn.fetchval("SELECT 1 FROM empire_alliance_members WHERE telegram_id=$1", req["requester_id"]):
                    await conn.execute("UPDATE empire_alliance_requests SET status='rejected',resolved_at=NOW() WHERE id=$1", request_id)
                    return {"status": "rejected", "alliance_name": req["name"], "player_id": int(req["requester_id"])}
                await conn.execute("INSERT INTO empire_alliance_members(alliance_id,telegram_id,role) VALUES($1,$2,'member')", req["alliance_id"], req["requester_id"])
                await conn.execute("INSERT INTO empire_alliance_history(alliance_id,event_type,title,description,actor_id) VALUES($1,'member_joined','عضو جدید پذیرفته شد',$2,$3)", int(req["alliance_id"]), f"شناسهٔ عضو: {int(req['requester_id'])}", leader_id)
                status = 'accepted'
            else:
                status = 'rejected'
            await conn.execute("UPDATE empire_alliance_requests SET status=$2,resolved_at=NOW() WHERE id=$1", request_id, status)
            return {"status": status, "alliance_name": req["name"], "player_id": int(req["requester_id"])}


async def leave_alliance(user_id: int):
    async with db().acquire() as conn:
        async with conn.transaction():
            member = await conn.fetchrow("""SELECT m.alliance_id,m.role,a.name,a.leader_id,
                (SELECT COUNT(*) FROM empire_alliance_members x WHERE x.alliance_id=m.alliance_id) AS member_count
                FROM empire_alliance_members m JOIN empire_alliances a ON a.id=m.alliance_id
                WHERE m.telegram_id=$1 FOR UPDATE OF m""", user_id)
            if not member:
                raise ValueError("عضو هیچ اتحادی نیستی.")
            if member["role"] == "leader" and int(member["member_count"]) > 1:
                raise ValueError("رهبر نمی‌تواند اتحاد چندنفره را ترک کند؛ ابتدا رهبری را منتقل کن. این قابلیت در نسخه بعدی اضافه می‌شود.")
            await conn.execute("INSERT INTO empire_alliance_history(alliance_id,event_type,title,description,actor_id) VALUES($1,'member_left','عضو اتحاد را ترک کرد',$2,$3)", int(member["alliance_id"]), f"شناسهٔ عضو: {user_id}", user_id)
            await conn.execute("DELETE FROM empire_alliance_members WHERE telegram_id=$1", user_id)
            await conn.execute("DELETE FROM empire_alliance_requests WHERE alliance_id=$1 AND status='pending'", member["alliance_id"])
            if member["role"] == "leader":
                await conn.execute("DELETE FROM empire_alliances WHERE id=$1", member["alliance_id"])
            return member["name"]


async def alliance_leaderboard(limit: int = 20):
    async with db().acquire() as conn:
        rows = await conn.fetch("""SELECT a.id,a.name,a.tag,COUNT(DISTINCT m.telegram_id)::int AS member_count,
            COUNT(DISTINCT c.city_key)::int AS cities_owned,COALESCE(SUM(c.price),0)::bigint AS territory_value
            FROM empire_alliances a LEFT JOIN empire_alliance_members m ON m.alliance_id=a.id
            LEFT JOIN empire_cities c ON c.owner_id=m.telegram_id
            GROUP BY a.id ORDER BY territory_value DESC,cities_owned DESC,member_count DESC LIMIT $1""", limit)
        return [dict(r) for r in rows]


async def player_leaderboard(limit: int = 20):
    async with db().acquire() as conn:
        rows = await conn.fetch("""SELECT u.telegram_id,u.display_name,u.games_played,u.wins,u.coins,
            COUNT(c.city_key)::int AS cities_owned,COALESCE(SUM(c.price),0)::bigint AS territory_value,
            COALESCE(ar.soldiers,0)::int AS soldiers
            FROM users u LEFT JOIN empire_cities c ON c.owner_id=u.telegram_id
            LEFT JOIN empire_armies ar ON ar.telegram_id=u.telegram_id
            WHERE u.is_banned=FALSE GROUP BY u.telegram_id,ar.soldiers
            ORDER BY territory_value DESC,cities_owned DESC,u.wins DESC,u.coins DESC LIMIT $1""", limit)
        return [dict(r) for r in rows]


async def alliance_members(user_id: int):
    async with db().acquire() as conn:
        alliance_id = await conn.fetchval("SELECT alliance_id FROM empire_alliance_members WHERE telegram_id=$1", user_id)
        if not alliance_id:
            raise ValueError("برای دیدن اعضا باید عضو یک اتحاد باشی.")
        rows = await conn.fetch("""SELECT m.telegram_id,m.role,m.rank,m.joined_at,u.display_name,u.username,
            COALESCE(c.cities,0)::int AS cities_owned
            FROM empire_alliance_members m JOIN users u ON u.telegram_id=m.telegram_id
            LEFT JOIN (SELECT owner_id,COUNT(*) AS cities FROM empire_cities WHERE owner_id IS NOT NULL GROUP BY owner_id) c ON c.owner_id=m.telegram_id
            WHERE m.alliance_id=$1 ORDER BY CASE WHEN m.role='leader' THEN 0 ELSE 1 END,m.joined_at ASC""", alliance_id)
        return [dict(r) for r in rows]


async def transfer_leadership(leader_id: int, new_leader_id: int):
    if leader_id == new_leader_id:
        raise ValueError("خودت همین حالا رهبر اتحادی.")
    async with db().acquire() as conn:
        async with conn.transaction():
            alliance = await conn.fetchrow("SELECT id,name FROM empire_alliances WHERE leader_id=$1 FOR UPDATE", leader_id)
            if not alliance:
                raise ValueError("فقط رهبر اتحاد می‌تواند رهبری را منتقل کند.")
            target = await conn.fetchval("SELECT 1 FROM empire_alliance_members WHERE alliance_id=$1 AND telegram_id=$2", alliance["id"], new_leader_id)
            if not target:
                raise ValueError("بازیکن انتخاب‌شده عضو اتحاد تو نیست.")
            await conn.execute("UPDATE empire_alliance_members SET role='member',rank=CASE WHEN rank='leader' THEN 'member' ELSE rank END WHERE alliance_id=$1 AND role='leader'", alliance["id"])
            await conn.execute("UPDATE empire_alliance_members SET role='leader',rank='leader' WHERE alliance_id=$1 AND telegram_id=$2", alliance["id"], new_leader_id)
            await conn.execute("UPDATE empire_alliances SET leader_id=$2 WHERE id=$1", alliance["id"], new_leader_id)
            return alliance["name"]


async def kick_member(leader_id: int, target_id: int):
    async with db().acquire() as conn:
        async with conn.transaction():
            alliance = await conn.fetchrow("SELECT id,name FROM empire_alliances WHERE leader_id=$1 FOR UPDATE", leader_id)
            if not alliance:
                raise ValueError("فقط رهبر اتحاد می‌تواند عضو اخراج کند.")
            if leader_id == target_id:
                raise ValueError("رهبر نمی‌تواند خودش را اخراج کند؛ از انتقال رهبری یا ترک اتحاد استفاده کن.")
            result = await conn.execute("DELETE FROM empire_alliance_members WHERE alliance_id=$1 AND telegram_id=$2 AND role='member'", alliance["id"], target_id)
            if result.endswith("0"):
                raise ValueError("این بازیکن عضو عادی اتحاد تو نیست.")
            await conn.execute("DELETE FROM empire_alliance_requests WHERE requester_id=$1 AND status='pending'", target_id)
            return alliance["name"]


async def send_alliance_message(user_id: int, message: str):
    message = " ".join(message.split()).strip()
    if not 1 <= len(message) <= 500:
        raise ValueError("پیام باید بین ۱ تا ۵۰۰ نویسه باشد.")
    async with db().acquire() as conn:
        alliance_id = await conn.fetchval("SELECT alliance_id FROM empire_alliance_members WHERE telegram_id=$1", user_id)
        if not alliance_id:
            raise ValueError("برای ارسال پیام باید عضو یک اتحاد باشی.")
        row = await conn.fetchrow("""INSERT INTO empire_alliance_messages(alliance_id,sender_id,message)
            VALUES($1,$2,$3) RETURNING id,created_at""", alliance_id, user_id, message)
        return {"id": int(row["id"]), "created_at": row["created_at"], "message": message}


async def alliance_messages(user_id: int, after_id: int = 0, limit: int = 50):
    async with db().acquire() as conn:
        alliance_id = await conn.fetchval("SELECT alliance_id FROM empire_alliance_members WHERE telegram_id=$1", user_id)
        if not alliance_id:
            raise ValueError("برای دیدن گفت‌وگو باید عضو یک اتحاد باشی.")
        rows = await conn.fetch("""SELECT x.id,x.sender_id,u.display_name AS sender_name,x.message,x.created_at
            FROM empire_alliance_messages x JOIN users u ON u.telegram_id=x.sender_id
            WHERE x.alliance_id=$1 AND x.id>$2 ORDER BY x.id ASC LIMIT $3""", alliance_id, after_id, min(max(limit,1),100))
        return [dict(r) for r in rows]


async def list_pacts(user_id: int):
    async with db().acquire() as conn:
        alliance_id = await conn.fetchval("SELECT alliance_id FROM empire_alliance_members WHERE telegram_id=$1", user_id)
        if not alliance_id:
            return []
        await conn.execute("UPDATE empire_alliance_pacts SET status='expired' WHERE status='active' AND expires_at<=NOW()")
        rows = await conn.fetch("""SELECT p.id,p.status,p.created_at,p.expires_at,p.initiated_by,
            CASE WHEN p.alliance_a=$1 THEN b.id ELSE a.id END AS other_id,
            CASE WHEN p.alliance_a=$1 THEN b.name ELSE a.name END AS other_name,
            CASE WHEN p.alliance_a=$1 THEN b.tag ELSE a.tag END AS other_tag
            FROM empire_alliance_pacts p JOIN empire_alliances a ON a.id=p.alliance_a JOIN empire_alliances b ON b.id=p.alliance_b
            WHERE (p.alliance_a=$1 OR p.alliance_b=$1) AND p.status IN ('pending','active')
            ORDER BY p.created_at DESC LIMIT 30""", alliance_id)
        return [dict(r) for r in rows]


async def offer_pact(leader_id: int, other_alliance_id: int):
    async with db().acquire() as conn:
        async with conn.transaction():
            own = await conn.fetchrow("SELECT id,name FROM empire_alliances WHERE leader_id=$1 FOR UPDATE", leader_id)
            if not own:
                raise ValueError("فقط رهبر اتحاد می‌تواند پیمان پیشنهاد کند.")
            if int(own["id"]) == other_alliance_id:
                raise ValueError("نمی‌توانی با اتحاد خودت پیمان ببندی.")
            other = await conn.fetchrow("SELECT id,name FROM empire_alliances WHERE id=$1", other_alliance_id)
            if not other:
                raise ValueError("اتحاد مقصد پیدا نشد.")
            a,b=sorted((int(own["id"]),other_alliance_id))
            try:
                row=await conn.fetchrow("""INSERT INTO empire_alliance_pacts(alliance_a,alliance_b,initiated_by)
                    VALUES($1,$2,$3) RETURNING id,expires_at""",a,b,own["id"])
            except Exception as exc:
                if getattr(exc,"sqlstate",None)=="23505":
                    raise ValueError("برای این دو اتحاد از قبل پیمان فعال یا درخواست در انتظار وجود دارد.") from exc
                raise
            return {"id":int(row["id"]),"other_name":other["name"],"expires_at":row["expires_at"]}


async def decide_pact(leader_id: int, pact_id: int, accept: bool):
    async with db().acquire() as conn:
        async with conn.transaction():
            pact=await conn.fetchrow("""SELECT p.id,p.alliance_a,p.alliance_b,p.initiated_by,p.status,a.name AS a_name,b.name AS b_name
                FROM empire_alliance_pacts p JOIN empire_alliances a ON a.id=p.alliance_a JOIN empire_alliances b ON b.id=p.alliance_b
                WHERE p.id=$1 FOR UPDATE OF p""",pact_id)
            if not pact or pact["status"]!='pending':
                raise ValueError("درخواست پیمان پیدا نشد یا قبلاً بررسی شده است.")
            own=await conn.fetchval("SELECT id FROM empire_alliances WHERE leader_id=$1",leader_id)
            if not own or int(own)==int(pact["initiated_by"]):
                raise ValueError("فقط رهبر اتحاد مقصد می‌تواند این پیمان را بررسی کند.")
            if int(own) not in (int(pact["alliance_a"]),int(pact["alliance_b"])):
                raise ValueError("این درخواست مربوط به اتحاد تو نیست.")
            status='active' if accept else 'rejected'
            await conn.execute("UPDATE empire_alliance_pacts SET status=$2,expires_at=CASE WHEN $2='active' THEN NOW()+INTERVAL '7 days' ELSE expires_at END WHERE id=$1",pact_id,status)
            return {"status":status,"other_name":pact["a_name"] if int(own)==int(pact["alliance_b"]) else pact["b_name"]}
