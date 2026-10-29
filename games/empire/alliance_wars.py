"""Alliance-vs-alliance territory wars for the Underworld Kings game."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
import random
from core.database import db
from games.empire.engine import WAR_PREPARATION_SECONDS, war_fee, war_attacker_wins, army_power_bonus
from games.empire.season_rules import current_season_key, defense_bonus_for_coins
from games.empire.alliance_economy_rules import war_loot_for_price


async def declare_alliance_war(user_id: int, target_city_key: str):
    async with db().acquire() as conn:
        async with conn.transaction():
            mine = await conn.fetchrow("""SELECT a.id,a.name,a.leader_id FROM empire_alliances a
                JOIN empire_alliance_members m ON m.alliance_id=a.id WHERE m.telegram_id=$1 FOR UPDATE OF a""", user_id)
            if not mine:
                raise ValueError("برای اعلام جنگ گروهی باید عضو یک اتحاد باشی.")
            if int(mine['leader_id']) != user_id:
                raise ValueError("فقط رهبر اتحاد می‌تواند جنگ اتحادها را اعلام کند.")
            target = await conn.fetchrow("SELECT * FROM empire_cities WHERE city_key=$1 FOR UPDATE", target_city_key)
            if not target or target['owner_id'] is None:
                raise ValueError("هدف باید قلمروی تصرف‌شدهٔ یک بازیکن باشد.")
            defender = await conn.fetchrow("""SELECT a.id,a.name,a.leader_id FROM empire_alliances a
                JOIN empire_alliance_members m ON m.alliance_id=a.id WHERE m.telegram_id=$1 FOR UPDATE OF a""", int(target['owner_id']))
            if not defender:
                raise ValueError("این قلمرو متعلق به بازیکنی است که عضو اتحاد نیست؛ جنگ اتحادها فقط میان دو اتحاد است.")
            if int(defender['id']) == int(mine['id']):
                raise ValueError("نمی‌توانی به قلمرو هم‌اتحادی حمله کنی.")
            shield = await conn.fetchval("SELECT shield_until>NOW() FROM empire_alliance_buildings WHERE alliance_id=$1", int(defender['id']))
            if shield:
                raise ValueError("اتحاد هدف سپر دفاعی فعال دارد؛ تا پایان سپر نمی‌توان به آن حمله کرد.")
            pact = await conn.fetchval("""SELECT 1 FROM empire_alliance_pacts WHERE status='active' AND expires_at>NOW()
                AND alliance_a=LEAST($1,$2) AND alliance_b=GREATEST($1,$2) LIMIT 1""", int(mine['id']), int(defender['id']))
            if pact:
                raise ValueError("بین این دو اتحاد پیمان عدم تجاوز فعال است.")
            pending = await conn.fetchval("SELECT id FROM empire_alliance_wars WHERE target_city_key=$1 AND status='pending'", target_city_key)
            if pending:
                raise ValueError(f"این قلمرو در جنگ اتحادها شمارهٔ {int(pending)} درگیر است.")
            fee = war_fee(int(target['price']))
            leader = await conn.fetchrow("SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE", user_id)
            if not leader or int(leader['coins']) < fee:
                raise ValueError(f"رهبر اتحاد برای اعلام جنگ به {fee} سکه نیاز دارد.")
            members = await conn.fetch("SELECT telegram_id FROM empire_alliance_members WHERE alliance_id=$1", int(mine['id']))
            ids = [int(r['telegram_id']) for r in members]
            city_count = int(await conn.fetchval("SELECT COUNT(*) FROM empire_cities WHERE owner_id=ANY($1::bigint[])", ids))
            soldiers = int(await conn.fetchval("SELECT COALESCE(SUM(soldiers),0) FROM empire_armies WHERE telegram_id=ANY($1::bigint[])", ids) or 0)
            academy_level = int(await conn.fetchval("SELECT COALESCE(academy_level,0) FROM empire_alliance_buildings WHERE alliance_id=$1", int(mine['id'])) or 0)
            attack = 50 + city_count * 15 + soldiers * 3 + academy_level * 15 + random.randint(0, 30)
            now = datetime.now(timezone.utc); resolves = now + timedelta(seconds=WAR_PREPARATION_SECONDS)
            await conn.execute("UPDATE users SET coins=coins-$2 WHERE telegram_id=$1", user_id, fee)
            await conn.execute("INSERT INTO empire_transactions(telegram_id,amount,reason) VALUES($1,$2,$3)", user_id, -fee, f"alliance_war_fee:{target_city_key}")
            row = await conn.fetchrow("""INSERT INTO empire_alliance_wars(attacker_alliance_id,defender_alliance_id,attacker_leader_id,
                defender_leader_id,target_city_key,attack_power,fee,resolves_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id""",
                int(mine['id']), int(defender['id']), user_id, int(defender['leader_id']), target_city_key, attack, fee, resolves)
            return {"id": int(row['id']), "attacker_alliance": mine['name'], "defender_alliance": defender['name'],
                    "target_name": target['name'], "target_city_key": target_city_key, "fee": fee,
                    "attack_power": attack, "resolves_at": resolves, "defender_leader_id": int(defender['leader_id']),
                    "attacker_leader_id": user_id}


async def alliance_war_history(user_id: int, limit: int = 20):
    async with db().acquire() as conn:
        return await conn.fetch("""SELECT w.*,aa.name AS attacker_name,da.name AS defender_name,c.name AS target_name
            FROM empire_alliance_wars w JOIN empire_alliances aa ON aa.id=w.attacker_alliance_id
            JOIN empire_alliances da ON da.id=w.defender_alliance_id JOIN empire_cities c ON c.city_key=w.target_city_key
            WHERE EXISTS(SELECT 1 FROM empire_alliance_members m WHERE m.alliance_id IN (w.attacker_alliance_id,w.defender_alliance_id) AND m.telegram_id=$1)
            ORDER BY w.created_at DESC LIMIT $2""", user_id, limit)



async def support_alliance_war(user_id: int, war_id: int, coins: int):
    """Spend coins to add defensive power to a pending war against the user's alliance."""
    bonus = defense_bonus_for_coins(coins)
    async with db().acquire() as conn:
        async with conn.transaction():
            war = await conn.fetchrow("SELECT * FROM empire_alliance_wars WHERE id=$1 FOR UPDATE", war_id)
            if not war or war['status'] != 'pending' or war['resolves_at'] <= datetime.now(timezone.utc):
                raise ValueError("این جنگ وجود ندارد یا مهلت کمک به آن تمام شده است.")
            membership = await conn.fetchrow("SELECT alliance_id FROM empire_alliance_members WHERE telegram_id=$1", user_id)
            if not membership or int(membership['alliance_id']) != int(war['defender_alliance_id']):
                raise ValueError("فقط اعضای اتحاد مدافع می‌توانند نیروی دفاعی بفرستند.")
            already = await conn.fetchval("SELECT 1 FROM empire_alliance_war_support WHERE war_id=$1 AND contributor_id=$2", war_id, user_id)
            if already:
                raise ValueError("قبلاً برای این جنگ کمک دفاعی فرستاده‌ای.")
            user = await conn.fetchrow("SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE", user_id)
            if not user or int(user['coins']) < coins:
                raise ValueError("سکهٔ کافی برای کمک دفاعی نداری.")
            await conn.execute("UPDATE users SET coins=coins-$2 WHERE telegram_id=$1", user_id, coins)
            await conn.execute("INSERT INTO empire_transactions(telegram_id,amount,reason) VALUES($1,$2,$3)", user_id, -coins, f"alliance_war_support:{war_id}")
            await conn.execute("INSERT INTO empire_alliance_war_support(war_id,contributor_id,coins,defense_bonus) VALUES($1,$2,$3,$4)", war_id, user_id, coins, bonus)
            total = int(await conn.fetchval("SELECT COALESCE(SUM(defense_bonus),0) FROM empire_alliance_war_support WHERE war_id=$1", war_id) or 0)
            return {"war_id": war_id, "coins_spent": coins, "defense_bonus": bonus, "total_defense_bonus": total}


async def alliance_season_leaderboard(limit: int = 10):
    season = current_season_key()
    async with db().acquire() as conn:
        rows = await conn.fetch("""SELECT s.alliance_id,a.name,a.tag,s.points,s.wins,s.losses,s.updated_at,
            (SELECT COUNT(*)::int FROM empire_alliance_members m WHERE m.alliance_id=a.id) AS member_count
            FROM empire_alliance_season_points s JOIN empire_alliances a ON a.id=s.alliance_id
            WHERE s.season_key=$1 ORDER BY s.points DESC,s.wins DESC,s.losses ASC,a.name LIMIT $2""", season, limit)
    return season, rows

async def resolve_expired_alliance_wars(limit: int = 20):
    async with db().acquire() as conn:
        ids = await conn.fetch("SELECT id FROM empire_alliance_wars WHERE status='pending' AND resolves_at<=NOW() ORDER BY resolves_at,id LIMIT $1", limit)
    results=[]
    for item in ids:
        async with db().acquire() as conn:
            async with conn.transaction():
                w=await conn.fetchrow("SELECT * FROM empire_alliance_wars WHERE id=$1 FOR UPDATE", int(item['id']))
                if not w or w['status']!='pending' or w['resolves_at']>datetime.now(timezone.utc):
                    continue
                target=await conn.fetchrow("SELECT * FROM empire_cities WHERE city_key=$1 FOR UPDATE", w['target_city_key'])
                base={"id":int(w['id']),"attacker_alliance_id":int(w['attacker_alliance_id']),"defender_alliance_id":int(w['defender_alliance_id']),"attacker_leader_id":int(w['attacker_leader_id']),"defender_leader_id":int(w['defender_leader_id']),"target_name":target['name'] if target else w['target_city_key']}
                if not target or target['owner_id'] is None:
                    await conn.execute("UPDATE empire_alliance_wars SET status='cancelled',resolved_at=NOW() WHERE id=$1",int(w['id']))
                    results.append({**base,"cancelled":True,"won":False,"attack_power":int(w['attack_power']),"defense_power":0})
                    continue
                defender=await conn.fetchrow("SELECT alliance_id FROM empire_alliance_members WHERE telegram_id=$1",int(target['owner_id']))
                if not defender or int(defender['alliance_id']) != int(w['defender_alliance_id']):
                    await conn.execute("UPDATE empire_alliance_wars SET status='cancelled',resolved_at=NOW() WHERE id=$1",int(w['id']))
                    results.append({**base,"cancelled":True,"won":False,"attack_power":int(w['attack_power']),"defense_power":0})
                    continue
                members=await conn.fetch("SELECT telegram_id FROM empire_alliance_members WHERE alliance_id=$1",int(w['defender_alliance_id']))
                ids=[int(r['telegram_id']) for r in members]
                cities=int(await conn.fetchval("SELECT COUNT(*) FROM empire_cities WHERE owner_id=ANY($1::bigint[])",ids))
                soldiers=int(await conn.fetchval("SELECT COALESCE(SUM(soldiers),0) FROM empire_armies WHERE telegram_id=ANY($1::bigint[])",ids) or 0)
                support_bonus=int(await conn.fetchval("SELECT COALESCE(SUM(defense_bonus),0) FROM empire_alliance_war_support WHERE war_id=$1",int(w['id'])) or 0)
                fortress_level=int(await conn.fetchval("SELECT COALESCE(fortress_level,0) FROM empire_alliance_buildings WHERE alliance_id=$1",int(w['defender_alliance_id'])) or 0)
                defense=50+max(1,cities)*15+int(target['defense_level'])*25+soldiers*3+fortress_level*25+support_bonus+random.randint(0,15)
                attack=int(w['attack_power']); won=war_attacker_wins(attack,defense); now=datetime.now(timezone.utc)
                season=current_season_key(now)
                attacker_points=3 if won else 1
                defender_points=1 if won else 3
                await conn.execute("""INSERT INTO empire_alliance_season_points(season_key,alliance_id,points,wins,losses,updated_at)
                    VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT(season_key,alliance_id) DO UPDATE SET
                    points=empire_alliance_season_points.points+EXCLUDED.points,
                    wins=empire_alliance_season_points.wins+EXCLUDED.wins,
                    losses=empire_alliance_season_points.losses+EXCLUDED.losses,updated_at=EXCLUDED.updated_at""",
                    season,int(w['attacker_alliance_id']),attacker_points,1 if won else 0,0 if won else 1,now)
                await conn.execute("""INSERT INTO empire_alliance_season_points(season_key,alliance_id,points,wins,losses,updated_at)
                    VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT(season_key,alliance_id) DO UPDATE SET
                    points=empire_alliance_season_points.points+EXCLUDED.points,
                    wins=empire_alliance_season_points.wins+EXCLUDED.wins,
                    losses=empire_alliance_season_points.losses+EXCLUDED.losses,updated_at=EXCLUDED.updated_at""",
                    season,int(w['defender_alliance_id']),defender_points,0 if won else 1,1 if won else 0,now)
                loot = 0
                if won:
                    await conn.execute("UPDATE empire_cities SET owner_id=$2,last_tax_at=NULL,updated_at=$3 WHERE city_key=$1",w['target_city_key'],int(w['attacker_leader_id']),now)
                    loot = war_loot_for_price(int(target['price']))
                    await conn.execute("INSERT INTO empire_alliance_treasuries(alliance_id,balance) VALUES($1,$2) ON CONFLICT(alliance_id) DO UPDATE SET balance=empire_alliance_treasuries.balance+EXCLUDED.balance,updated_at=NOW()", int(w['attacker_alliance_id']), loot)
                    await conn.execute("INSERT INTO empire_alliance_treasury_transactions(alliance_id,actor_id,amount,reason) VALUES($1,$2,$3,'war_loot')", int(w['attacker_alliance_id']), int(w['attacker_leader_id']), loot)
                    status='attacker_won'
                else: status='defender_won'
                await conn.execute("UPDATE empire_alliance_wars SET status=$2,defense_power=$3,resolved_at=$4 WHERE id=$1",int(w['id']),status,defense,now)
                results.append({**base,"cancelled":False,"won":won,"loot":loot,"attack_power":attack,"defense_power":defense,
                                "attacker_alliance_id":int(w['attacker_alliance_id']),"defender_alliance_id":int(w['defender_alliance_id']),"support_bonus":support_bonus,"season_key":season})
    return results
