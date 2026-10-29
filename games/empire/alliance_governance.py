"""Alliance event history and internal democratic proposals (v0.29)."""
from __future__ import annotations
from core.database import db


from games.empire.alliance_governance_rules import validate_proposal


async def record_event(alliance_id: int, event_type: str, title: str, description: str = "", actor_id: int | None = None):
    async with db().acquire() as conn:
        await conn.execute("""INSERT INTO empire_alliance_history(alliance_id,event_type,title,description,actor_id)
            VALUES($1,$2,$3,$4,$5)""", alliance_id, event_type[:40], title[:120], description[:1000], actor_id)


async def history(user_id: int, limit: int = 50):
    async with db().acquire() as conn:
        aid = await conn.fetchval("SELECT alliance_id FROM empire_alliance_members WHERE telegram_id=$1", user_id)
        if not aid:
            raise ValueError("برای دیدن تاریخچه باید عضو یک اتحاد باشی.")
        rows = await conn.fetch("""SELECT h.id,h.event_type,h.title,h.description,h.actor_id,
            COALESCE(u.display_name,'عضو سابق') AS actor_name,h.created_at
            FROM empire_alliance_history h LEFT JOIN users u ON u.telegram_id=h.actor_id
            WHERE h.alliance_id=$1 ORDER BY h.id DESC LIMIT $2""", int(aid), min(max(int(limit),1),100))
        return [dict(r) for r in rows]


async def create_proposal(user_id: int, title: str, description: str, duration_hours: int = 24):
    title, description, duration_hours = validate_proposal(title, description, duration_hours)
    async with db().acquire() as conn:
        async with conn.transaction():
            member = await conn.fetchrow("""SELECT m.alliance_id,m.rank,a.name FROM empire_alliance_members m
                JOIN empire_alliances a ON a.id=m.alliance_id WHERE m.telegram_id=$1 FOR UPDATE OF m""", user_id)
            if not member:
                raise ValueError("برای ایجاد پیشنهاد باید عضو اتحاد باشی.")
            if member['rank'] not in ('leader','officer'):
                raise ValueError("فقط رهبر یا افسر اتحاد می‌تواند رأی‌گیری ایجاد کند.")
            active = await conn.fetchval("SELECT COUNT(*) FROM empire_alliance_proposals WHERE alliance_id=$1 AND status='open' AND expires_at>NOW()", int(member['alliance_id']))
            if int(active) >= 5:
                raise ValueError("حداکثر ۵ رأی‌گیری باز هم‌زمان مجاز است.")
            row = await conn.fetchrow("""INSERT INTO empire_alliance_proposals(alliance_id,creator_id,title,description,expires_at)
                VALUES($1,$2,$3,$4,NOW()+($5::text||' hours')::interval) RETURNING id,expires_at,created_at""",
                int(member['alliance_id']), user_id, title, description, duration_hours)
            await conn.execute("""INSERT INTO empire_alliance_history(alliance_id,event_type,title,description,actor_id)
                VALUES($1,'vote_created',$2,$3,$4)""", int(member['alliance_id']), 'رأی‌گیری جدید: '+title, f'مدت: {duration_hours} ساعت', user_id)
            return {'id': int(row['id']), 'title': title, 'description': description,
                    'expires_at': row['expires_at'], 'created_at': row['created_at'], 'status':'open'}


async def list_proposals(user_id: int, limit: int = 30):
    async with db().acquire() as conn:
        aid = await conn.fetchval("SELECT alliance_id FROM empire_alliance_members WHERE telegram_id=$1", user_id)
        if not aid:
            raise ValueError("برای دیدن رأی‌گیری‌ها باید عضو یک اتحاد باشی.")
        await conn.execute("UPDATE empire_alliance_proposals SET status=CASE WHEN yes_votes>no_votes THEN 'passed' ELSE 'rejected' END WHERE alliance_id=$1 AND status='open' AND expires_at<=NOW()", int(aid))
        rows = await conn.fetch("""SELECT p.id,p.creator_id,COALESCE(u.display_name,'عضو سابق') AS creator_name,
            p.title,p.description,p.status,p.expires_at,p.created_at,p.yes_votes,p.no_votes,
            (SELECT COUNT(*) FROM empire_alliance_members m WHERE m.alliance_id=p.alliance_id)::int AS eligible_voters,
            (SELECT v.choice FROM empire_alliance_votes v WHERE v.proposal_id=p.id AND v.voter_id=$2) AS my_vote
            FROM empire_alliance_proposals p LEFT JOIN users u ON u.telegram_id=p.creator_id
            WHERE p.alliance_id=$1 ORDER BY p.id DESC LIMIT $3""", int(aid), user_id, min(max(int(limit),1),50))
        return [dict(r) for r in rows]


async def cast_vote(user_id: int, proposal_id: int, choice: str):
    if choice not in ('yes','no'):
        raise ValueError("رأی باید موافق یا مخالف باشد.")
    async with db().acquire() as conn:
        async with conn.transaction():
            member = await conn.fetchrow("SELECT alliance_id FROM empire_alliance_members WHERE telegram_id=$1 FOR UPDATE", user_id)
            if not member:
                raise ValueError("برای رأی‌دادن باید عضو اتحاد باشی.")
            p = await conn.fetchrow("SELECT id,alliance_id,title,status,expires_at FROM empire_alliance_proposals WHERE id=$1 FOR UPDATE", proposal_id)
            if not p or int(p['alliance_id']) != int(member['alliance_id']):
                raise ValueError("رأی‌گیری متعلق به اتحاد تو نیست یا پیدا نشد.")
            if p['status'] != 'open' or p['expires_at'] <= await conn.fetchval('SELECT NOW()'):
                raise ValueError("مهلت این رأی‌گیری تمام شده است.")
            exists = await conn.fetchval("SELECT 1 FROM empire_alliance_votes WHERE proposal_id=$1 AND voter_id=$2", proposal_id, user_id)
            if exists:
                raise ValueError("قبلاً در این رأی‌گیری شرکت کرده‌ای؛ رأی قابل تغییر نیست.")
            await conn.execute("INSERT INTO empire_alliance_votes(proposal_id,voter_id,choice) VALUES($1,$2,$3)", proposal_id, user_id, choice)
            await conn.execute("UPDATE empire_alliance_proposals SET yes_votes=yes_votes+CASE WHEN $2::text='yes' THEN 1 ELSE 0 END,no_votes=no_votes+CASE WHEN $2::text='no' THEN 1 ELSE 0 END WHERE id=$1", proposal_id, choice)
            await conn.execute("""INSERT INTO empire_alliance_history(alliance_id,event_type,title,description,actor_id)
                VALUES($1,'vote_cast',$2,$3,$4)""", int(member['alliance_id']), 'ثبت رأی: '+str(p['title']), 'رأی '+('موافق' if choice=='yes' else 'مخالف'), user_id)
            counts = await conn.fetchrow("SELECT yes_votes,no_votes FROM empire_alliance_proposals WHERE id=$1", proposal_id)
            return {'proposal_id': proposal_id, 'choice': choice, 'yes_votes': int(counts['yes_votes']), 'no_votes': int(counts['no_votes'])}
