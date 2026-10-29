"""Alliance internal ranks and treasury audit history (v0.27)."""
from core.database import db

RANKS = {
    "commander": "فرمانده",
    "treasurer": "خزانه‌دار",
    "officer": "افسر",
    "member": "عضو عادی",
}

async def set_member_rank(leader_id: int, target_id: int, rank: str):
    if rank not in RANKS:
        raise ValueError("رتبهٔ انتخاب‌شده معتبر نیست؛ رتبهٔ رهبر قابل واگذاری نیست.")
    if target_id == leader_id:
        raise ValueError("رهبر نمی‌تواند رتبهٔ خودش را تغییر دهد.")
    async with db().acquire() as conn:
        async with conn.transaction():
            alliance = await conn.fetchrow("SELECT id,name FROM empire_alliances WHERE leader_id=$1 FOR UPDATE", leader_id)
            if not alliance:
                raise ValueError("فقط رهبر اتحاد می‌تواند رتبهٔ اعضا را تغییر دهد.")
            result = await conn.execute("UPDATE empire_alliance_members SET rank=$3 WHERE alliance_id=$1 AND telegram_id=$2 AND role='member'", int(alliance['id']), target_id, rank)
            if result.endswith('0'):
                raise ValueError("عضو موردنظر پیدا نشد یا رتبهٔ او قابل تغییر نیست.")
            await conn.execute("INSERT INTO empire_alliance_rank_log(alliance_id,actor_id,target_id,new_rank) VALUES($1,$2,$3,$4)", int(alliance['id']), leader_id, target_id, rank)
            return {"alliance_name": alliance['name'], "telegram_id": target_id, "rank": rank, "rank_name": RANKS[rank]}

async def finance_history(user_id: int, limit: int = 30):
    async with db().acquire() as conn:
        alliance_id = await conn.fetchval("SELECT alliance_id FROM empire_alliance_members WHERE telegram_id=$1", user_id)
        if not alliance_id:
            raise ValueError("برای دیدن گزارش مالی باید عضو یک اتحاد باشی.")
        rows = await conn.fetch("""SELECT t.id,t.actor_id,u.display_name,t.amount,t.reason,t.created_at
            FROM empire_alliance_treasury_transactions t JOIN users u ON u.telegram_id=t.actor_id
            WHERE t.alliance_id=$1 ORDER BY t.id DESC LIMIT $2""", int(alliance_id), min(max(limit,1),100))
        return [dict(r) for r in rows]
