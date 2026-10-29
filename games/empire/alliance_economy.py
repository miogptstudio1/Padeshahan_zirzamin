"""Alliance treasury, daily rewards, and member contribution reports."""
from __future__ import annotations
from core.database import db
from games.empire.alliance_economy_rules import DAILY_REWARD, MIN_TRANSFER, MAX_TRANSFER, validate_transfer_amount


async def treasury_summary(user_id: int):
    async with db().acquire() as conn:
        member = await conn.fetchrow("""SELECT a.id,a.name,a.tag,a.leader_id,m.role,m.rank,
            COALESCE(t.balance,0)::bigint AS balance
            FROM empire_alliance_members m JOIN empire_alliances a ON a.id=m.alliance_id
            LEFT JOIN empire_alliance_treasuries t ON t.alliance_id=a.id
            WHERE m.telegram_id=$1""", user_id)
        if not member:
            raise ValueError("برای مشاهدهٔ خزانه باید عضو یک اتحاد باشی.")
        rows = await conn.fetch("""SELECT id,amount,reason,created_at FROM empire_alliance_treasury_transactions
            WHERE alliance_id=$1 ORDER BY id DESC LIMIT 10""", member['id'])
        claim = await conn.fetchrow("SELECT claimed_at FROM empire_alliance_daily_claims WHERE telegram_id=$1", user_id)
        return {"alliance_id": int(member['id']), "alliance_name": member['name'], "tag": member['tag'],
                "leader_id": int(member['leader_id']), "is_leader": int(member['leader_id']) == user_id, "is_treasurer": member['rank'] == "treasurer", "rank": member['rank'],
                "balance": int(member['balance']), "daily_reward": DAILY_REWARD,
                "last_daily_claim": claim['claimed_at'] if claim else None,
                "transactions": [dict(r) for r in rows]}


async def deposit(user_id: int, amount: int):
    validate_transfer_amount(amount)
    async with db().acquire() as conn:
        async with conn.transaction():
            member = await conn.fetchrow("SELECT alliance_id FROM empire_alliance_members WHERE telegram_id=$1 FOR UPDATE", user_id)
            if not member:
                raise ValueError("برای واریز باید عضو یک اتحاد باشی.")
            user = await conn.fetchrow("SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE", user_id)
            if not user or int(user['coins']) < amount:
                raise ValueError("موجودی سکه برای این واریز کافی نیست.")
            await conn.execute("UPDATE users SET coins=coins-$2 WHERE telegram_id=$1", user_id, amount)
            await conn.execute("INSERT INTO empire_transactions(telegram_id,amount,reason) VALUES($1,$2,$3)", user_id, -amount, f"alliance_treasury_deposit:{int(member['alliance_id'])}")
            await conn.execute("INSERT INTO empire_alliance_treasuries(alliance_id,balance) VALUES($1,$2) ON CONFLICT(alliance_id) DO UPDATE SET balance=empire_alliance_treasuries.balance+EXCLUDED.balance,updated_at=NOW()", int(member['alliance_id']), amount)
            await conn.execute("INSERT INTO empire_alliance_treasury_transactions(alliance_id,actor_id,amount,reason) VALUES($1,$2,$3,'deposit')", int(member['alliance_id']), user_id, amount)
            balance = int(await conn.fetchval("SELECT balance FROM empire_alliance_treasuries WHERE alliance_id=$1", int(member['alliance_id'])))
            return {"amount": amount, "treasury_balance": balance, "coins": int(user['coins'])-amount}


async def withdraw(user_id: int, amount: int):
    validate_transfer_amount(amount)
    async with db().acquire() as conn:
        async with conn.transaction():
            alliance = await conn.fetchrow("""SELECT a.id,a.name,m.rank FROM empire_alliance_members m
                JOIN empire_alliances a ON a.id=m.alliance_id WHERE m.telegram_id=$1 FOR UPDATE OF a,m""", user_id)
            if not alliance or alliance["rank"] not in ("leader", "treasurer"):
                raise ValueError("فقط رهبر یا خزانه‌دار اتحاد می‌تواند از خزانه برداشت کند.")
            treasury = await conn.fetchrow("SELECT balance FROM empire_alliance_treasuries WHERE alliance_id=$1 FOR UPDATE", int(alliance['id']))
            if not treasury or int(treasury['balance']) < amount:
                raise ValueError("موجودی خزانه برای این برداشت کافی نیست.")
            await conn.execute("UPDATE empire_alliance_treasuries SET balance=balance-$2,updated_at=NOW() WHERE alliance_id=$1", int(alliance['id']), amount)
            row = await conn.fetchrow("UPDATE users SET coins=coins+$2 WHERE telegram_id=$1 RETURNING coins", user_id, amount)
            await conn.execute("INSERT INTO empire_transactions(telegram_id,amount,reason) VALUES($1,$2,$3)", user_id, amount, f"alliance_treasury_withdraw:{int(alliance['id'])}")
            await conn.execute("INSERT INTO empire_alliance_treasury_transactions(alliance_id,actor_id,amount,reason) VALUES($1,$2,$3,'withdraw')", int(alliance['id']), user_id, -amount)
            balance = int(await conn.fetchval("SELECT balance FROM empire_alliance_treasuries WHERE alliance_id=$1", int(alliance['id'])))
            return {"amount": amount, "treasury_balance": balance, "coins": int(row['coins']), "alliance_name": alliance['name']}


async def claim_daily_bonus(user_id: int):
    async with db().acquire() as conn:
        async with conn.transaction():
            member = await conn.fetchrow("""SELECT a.id,a.name FROM empire_alliance_members m
                JOIN empire_alliances a ON a.id=m.alliance_id WHERE m.telegram_id=$1 FOR UPDATE OF a""", user_id)
            if not member:
                raise ValueError("برای دریافت پاداش اتحاد باید عضو یک اتحاد باشی.")
            member_count = int(await conn.fetchval("SELECT COUNT(*) FROM empire_alliance_members WHERE alliance_id=$1", int(member['id'])))
            if member_count < 2:
                raise ValueError("پاداش روزانه فقط برای اتحادهای دارای دست‌کم دو عضو فعال است.")
            claimed = await conn.fetchrow("""INSERT INTO empire_alliance_daily_claims(telegram_id,alliance_id,claimed_at)
                VALUES($1,$2,NOW()) ON CONFLICT(telegram_id) DO UPDATE SET alliance_id=EXCLUDED.alliance_id,claimed_at=NOW()
                WHERE empire_alliance_daily_claims.claimed_at <= NOW()-INTERVAL '24 hours' RETURNING claimed_at""", user_id, int(member['id']))
            if not claimed:
                last = await conn.fetchval("SELECT claimed_at FROM empire_alliance_daily_claims WHERE telegram_id=$1", user_id)
                raise ValueError(f"پاداش قبلاً دریافت شده؛ زمان دریافت بعدی: {last.astimezone().strftime('%H:%M %Y-%m-%d')} به وقت محلی.")
            row = await conn.fetchrow("UPDATE users SET coins=coins+$2 WHERE telegram_id=$1 RETURNING coins", user_id, DAILY_REWARD)
            await conn.execute("INSERT INTO empire_transactions(telegram_id,amount,reason) VALUES($1,$2,$3)", user_id, DAILY_REWARD, f"alliance_daily_reward:{int(member['id'])}")
            return {"reward": DAILY_REWARD, "coins": int(row['coins']), "alliance_name": member['name'], "claimed_at": claimed['claimed_at']}


async def member_contributions(user_id: int):
    async with db().acquire() as conn:
        alliance_id = await conn.fetchval("SELECT alliance_id FROM empire_alliance_members WHERE telegram_id=$1", user_id)
        if not alliance_id:
            raise ValueError("برای مشاهدهٔ مشارکت‌ها باید عضو یک اتحاد باشی.")
        rows = await conn.fetch("""SELECT m.telegram_id,m.role,u.display_name,
            COALESCE(s.support_coins,0)::bigint AS support_coins,COALESCE(s.support_count,0)::int AS support_count,
            COALESCE(t.deposits,0)::bigint AS treasury_deposits,COALESCE(c.city_count,0)::int AS cities_owned,
            COALESCE(ar.soldiers,0)::int AS soldiers
            FROM empire_alliance_members m JOIN users u ON u.telegram_id=m.telegram_id
            LEFT JOIN (SELECT ws.contributor_id,SUM(ws.coins) AS support_coins,COUNT(*) AS support_count FROM empire_alliance_war_support ws JOIN empire_alliance_wars w ON w.id=ws.war_id WHERE w.defender_alliance_id=$1 GROUP BY ws.contributor_id) s ON s.contributor_id=m.telegram_id
            LEFT JOIN (SELECT actor_id,SUM(amount) AS deposits FROM empire_alliance_treasury_transactions WHERE alliance_id=$1 AND reason='deposit' GROUP BY actor_id) t ON t.actor_id=m.telegram_id
            LEFT JOIN (SELECT owner_id,COUNT(*) AS city_count FROM empire_cities WHERE owner_id IS NOT NULL GROUP BY owner_id) c ON c.owner_id=m.telegram_id
            LEFT JOIN empire_armies ar ON ar.telegram_id=m.telegram_id
            WHERE m.alliance_id=$1 ORDER BY COALESCE(s.support_coins,0)+COALESCE(t.deposits,0) DESC,m.joined_at ASC""", int(alliance_id))
        return [dict(r) for r in rows]
