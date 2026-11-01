"""PostgreSQL-backed Empire economy and city ownership operations."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
import random
from core.database import db
from games.empire.equipment_rules import item_stats
from games.empire import army_advanced
from games.empire.engine import (
    ASSETS, CITIES, DAILY_REWARD, WORK_REWARD, WORK_COOLDOWN_SECONDS,
    DAILY_COOLDOWN_SECONDS, MAX_ASSET_LEVEL, MAX_DEFENSE_LEVEL,
    TAX_COOLDOWN_SECONDS, asset_cost, hourly_income, defense_upgrade_cost,
    WAR_PREPARATION_SECONDS, war_fee, attack_power, defense_power, war_attacker_wins,
    SOLDIER_RECRUIT_COST, MAX_SOLDIERS, recruit_cost, army_power_bonus,
)


def _epoch(value):
    return value.timestamp() if value else None


async def claim_daily(user_id: int) -> tuple[int, int]:
    async with db().acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT coins,daily_claimed_at FROM users WHERE telegram_id=$1 FOR UPDATE", user_id)
            if not row: raise ValueError("ابتدا در خصوصی ربات /start را بزن.")
            now = datetime.now(timezone.utc); last = row['daily_claimed_at']
            if last and (now-last).total_seconds() < DAILY_COOLDOWN_SECONDS:
                remain = int(DAILY_COOLDOWN_SECONDS-(now-last).total_seconds())
                raise ValueError(f"پاداش روزانه را قبلاً گرفتی؛ حدود {max(1,remain//3600)} ساعت دیگر برگرد.")
            balance = int(row['coins']) + DAILY_REWARD
            await conn.execute("UPDATE users SET coins=$2,daily_claimed_at=$3 WHERE telegram_id=$1", user_id,balance,now)
            await conn.execute("INSERT INTO empire_transactions(telegram_id,amount,reason) VALUES($1,$2,'daily')",user_id,DAILY_REWARD)
            return DAILY_REWARD,balance


async def work(user_id: int) -> tuple[int, int]:
    async with db().acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT coins,work_claimed_at FROM users WHERE telegram_id=$1 FOR UPDATE",user_id)
            if not row: raise ValueError("ابتدا در خصوصی ربات /start را بزن.")
            now=datetime.now(timezone.utc); last=row['work_claimed_at']
            if last and (now-last).total_seconds() < WORK_COOLDOWN_SECONDS:
                remain=int(WORK_COOLDOWN_SECONDS-(now-last).total_seconds())
                raise ValueError(f"هنوز خسته‌ای! {max(1,remain//60)} دقیقهٔ دیگر دوباره کار کن.")
            balance=int(row['coins'])+WORK_REWARD
            await conn.execute("UPDATE users SET coins=$2,work_claimed_at=$3 WHERE telegram_id=$1",user_id,balance,now)
            await conn.execute("INSERT INTO empire_transactions(telegram_id,amount,reason) VALUES($1,$2,'work')",user_id,WORK_REWARD)
            return WORK_REWARD,balance


async def assets_for(user_id: int):
    async with db().acquire() as conn:
        return await conn.fetch("SELECT asset_key,level,last_collected_at FROM empire_assets WHERE telegram_id=$1 ORDER BY asset_key",user_id)


async def buy_or_upgrade(user_id: int, asset_key: str) -> tuple[str,int,int,int]:
    if asset_key not in ASSETS: raise ValueError("دارایی نامعتبر است. یکی از workshop، club یا factory را انتخاب کن.")
    async with db().acquire() as conn:
        async with conn.transaction():
            user=await conn.fetchrow("SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE",user_id)
            if not user: raise ValueError("ابتدا در خصوصی ربات /start را بزن.")
            owned=await conn.fetchrow("SELECT level FROM empire_assets WHERE telegram_id=$1 AND asset_key=$2 FOR UPDATE",user_id,asset_key)
            level=int(owned['level']) if owned else 0; cost=asset_cost(asset_key,level)
            if int(user['coins']) < cost: raise ValueError(f"سکه کافی نیست؛ هزینهٔ این خرید/ارتقا {cost} سکه است.")
            new_level=level+1; balance=int(user['coins'])-cost
            await conn.execute("UPDATE users SET coins=$2 WHERE telegram_id=$1",user_id,balance)
            await conn.execute("""INSERT INTO empire_assets(telegram_id,asset_key,level,last_collected_at) VALUES($1,$2,$3,NULL)
                ON CONFLICT(telegram_id,asset_key) DO UPDATE SET level=EXCLUDED.level""",user_id,asset_key,new_level)
            await conn.execute("INSERT INTO empire_transactions(telegram_id,amount,reason) VALUES($1,$2,$3)",user_id,-cost,f"buy:{asset_key}:level:{new_level}")
            return ASSETS[asset_key]['name'],new_level,cost,balance


async def collect_income(user_id: int, asset_key: str) -> tuple[str,int,int]:
    if asset_key not in ASSETS: raise ValueError("دارایی نامعتبر است. از workshop، club یا factory استفاده کن.")
    async with db().acquire() as conn:
        async with conn.transaction():
            user=await conn.fetchrow("SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE",user_id)
            if not user: raise ValueError("ابتدا /start را بزن.")
            asset=await conn.fetchrow("SELECT level,last_collected_at FROM empire_assets WHERE telegram_id=$1 AND asset_key=$2 FOR UPDATE",user_id,asset_key)
            if not asset: raise ValueError("این دارایی را نداری؛ ابتدا آن را بخر.")
            now=datetime.now(timezone.utc); last=asset['last_collected_at']
            if last and (now-last).total_seconds() < 3600:
                remain=int(3600-(now-last).total_seconds())
                raise ValueError(f"درآمد این دارایی هنوز آماده نیست؛ {max(1,remain//60)} دقیقهٔ دیگر تلاش کن.")
            amount=hourly_income(asset_key,int(asset['level'])); balance=int(user['coins'])+amount
            await conn.execute("UPDATE users SET coins=$2 WHERE telegram_id=$1",user_id,balance)
            await conn.execute("UPDATE empire_assets SET last_collected_at=$3 WHERE telegram_id=$1 AND asset_key=$2",user_id,asset_key,now)
            await conn.execute("INSERT INTO empire_transactions(telegram_id,amount,reason) VALUES($1,$2,$3)",user_id,amount,f"collect:{asset_key}")
            return ASSETS[asset_key]['name'],amount,balance


async def leaderboard(limit: int = 10):
    async with db().acquire() as conn:
        return await conn.fetch("""SELECT u.telegram_id,u.display_name,u.coins,COUNT(a.asset_key)::int AS assets,
            COALESCE(SUM(a.level),0)::int AS levels FROM users u LEFT JOIN empire_assets a ON a.telegram_id=u.telegram_id
            GROUP BY u.telegram_id,u.display_name,u.coins ORDER BY u.coins DESC,levels DESC LIMIT $1""",limit)


async def cities_list():
    async with db().acquire() as conn:
        return await conn.fetch("""SELECT c.*,u.display_name AS owner_name FROM empire_cities c
            LEFT JOIN users u ON u.telegram_id=c.owner_id ORDER BY c.price""")


async def city_buy(user_id: int, city_key: str) -> tuple[str,int,int]:
    if city_key not in CITIES: raise ValueError("نام قلمرو نامعتبر است. از /empire_cities لیست را ببین.")
    async with db().acquire() as conn:
        async with conn.transaction():
            user=await conn.fetchrow("SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE",user_id)
            if not user: raise ValueError("ابتدا در خصوصی ربات /start را بزن.")
            city=await conn.fetchrow("SELECT * FROM empire_cities WHERE city_key=$1 FOR UPDATE",city_key)
            if not city: raise ValueError("این قلمرو وجود ندارد.")
            if city['owner_id'] is not None: raise ValueError("این قلمرو قبلاً تصرف شده است.")
            price=int(city['price'])
            if int(user['coins']) < price: raise ValueError(f"سکه کافی نیست؛ قیمت این قلمرو {price} سکه است.")
            balance=int(user['coins'])-price; now=datetime.now(timezone.utc)
            await conn.execute("UPDATE users SET coins=$2 WHERE telegram_id=$1",user_id,balance)
            await conn.execute("UPDATE empire_cities SET owner_id=$2,defense_level=0,last_tax_at=NULL,updated_at=$3 WHERE city_key=$1",city_key,user_id,now)
            await conn.execute("INSERT INTO empire_transactions(telegram_id,amount,reason) VALUES($1,$2,$3)",user_id,-price,f"city_buy:{city_key}")
            return city['name'],price,balance


async def collect_tax(user_id: int, city_key: str) -> tuple[str,int,int]:
    if city_key not in CITIES: raise ValueError("قلمرو نامعتبر است.")
    async with db().acquire() as conn:
        async with conn.transaction():
            user=await conn.fetchrow("SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE",user_id)
            if not user: raise ValueError("ابتدا /start را بزن.")
            city=await conn.fetchrow("SELECT * FROM empire_cities WHERE city_key=$1 FOR UPDATE",city_key)
            if not city or city['owner_id'] != user_id: raise ValueError("این قلمرو متعلق به تو نیست.")
            now=datetime.now(timezone.utc); last=city['last_tax_at']
            if last and (now-last).total_seconds() < TAX_COOLDOWN_SECONDS:
                remain=int(TAX_COOLDOWN_SECONDS-(now-last).total_seconds())
                raise ValueError(f"مالیات هنوز آماده نیست؛ حدود {max(1,remain//3600)} ساعت دیگر تلاش کن.")
            amount=int(city['tax_income']); balance=int(user['coins'])+amount
            await conn.execute("UPDATE users SET coins=$2 WHERE telegram_id=$1",user_id,balance)
            await conn.execute("UPDATE empire_cities SET last_tax_at=$2,updated_at=$2 WHERE city_key=$1",city_key,now)
            await conn.execute("INSERT INTO empire_transactions(telegram_id,amount,reason) VALUES($1,$2,$3)",user_id,amount,f"city_tax:{city_key}")
            return city['name'],amount,balance


async def upgrade_city_defense(user_id: int, city_key: str) -> tuple[str,int,int,int]:
    if city_key not in CITIES: raise ValueError("قلمرو نامعتبر است.")
    async with db().acquire() as conn:
        async with conn.transaction():
            user=await conn.fetchrow("SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE",user_id)
            if not user: raise ValueError("ابتدا /start را بزن.")
            city=await conn.fetchrow("SELECT * FROM empire_cities WHERE city_key=$1 FOR UPDATE",city_key)
            if not city or city['owner_id'] != user_id: raise ValueError("فقط مالک قلمرو می‌تواند دفاعش را ارتقا دهد.")
            level=int(city['defense_level']); cost=defense_upgrade_cost(city_key,level)
            if int(user['coins']) < cost: raise ValueError(f"سکه کافی نیست؛ هزینهٔ ارتقای دفاع {cost} سکه است.")
            new_level=level+1; balance=int(user['coins'])-cost; now=datetime.now(timezone.utc)
            await conn.execute("UPDATE users SET coins=$2 WHERE telegram_id=$1",user_id,balance)
            await conn.execute("UPDATE empire_cities SET defense_level=$2,updated_at=$3 WHERE city_key=$1",city_key,new_level,now)
            await conn.execute("INSERT INTO empire_transactions(telegram_id,amount,reason) VALUES($1,$2,$3)",user_id,-cost,f"city_defense:{city_key}:level:{new_level}")
            return city['name'],new_level,cost,balance


async def my_cities(user_id: int):
    async with db().acquire() as conn:
        return await conn.fetch("SELECT * FROM empire_cities WHERE owner_id=$1 ORDER BY price",user_id)


async def city_leaderboard(limit: int = 10):
    async with db().acquire() as conn:
        return await conn.fetch("""SELECT u.telegram_id,u.display_name,COUNT(c.city_key)::int AS city_count,
            COALESCE(SUM(c.tax_income),0)::bigint AS tax_total,COALESCE(SUM(c.defense_level),0)::int AS defense_total
            FROM users u JOIN empire_cities c ON c.owner_id=u.telegram_id GROUP BY u.telegram_id,u.display_name
            ORDER BY city_count DESC,tax_total DESC LIMIT $1""",limit)


async def army_for(user_id: int):
    async with db().acquire() as conn:
        row = await conn.fetchrow("SELECT soldiers,updated_at FROM empire_armies WHERE telegram_id=$1", user_id)
        return {"soldiers": int(row["soldiers"]), "updated_at": row["updated_at"]} if row else {"soldiers": 0, "updated_at": None}


async def recruit_soldiers(user_id: int, count: int) -> tuple[int, int, int]:
    cost = recruit_cost(count)
    async with db().acquire() as conn:
        async with conn.transaction():
            user = await conn.fetchrow("SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE", user_id)
            if not user:
                raise ValueError("ابتدا در خصوصی ربات /start را بزن.")
            army = await conn.fetchrow("SELECT soldiers FROM empire_armies WHERE telegram_id=$1 FOR UPDATE", user_id)
            current = int(army["soldiers"]) if army else 0
            if current + count > MAX_SOLDIERS:
                raise ValueError(f"حداکثر ارتش {MAX_SOLDIERS} سرباز است؛ اکنون {current} سرباز داری.")
            if int(user["coins"]) < cost:
                raise ValueError(f"سکه کافی نیست؛ استخدام {count} سرباز {cost} سکه هزینه دارد.")
            balance = int(user["coins"]) - cost
            now = datetime.now(timezone.utc)
            await conn.execute("UPDATE users SET coins=$2 WHERE telegram_id=$1", user_id, balance)
            await conn.execute("""INSERT INTO empire_armies(telegram_id,soldiers,updated_at) VALUES($1,$2,$3)
                ON CONFLICT(telegram_id) DO UPDATE SET soldiers=empire_armies.soldiers + EXCLUDED.soldiers, updated_at=EXCLUDED.updated_at""", user_id, count, now)
            await conn.execute("INSERT INTO empire_transactions(telegram_id,amount,reason) VALUES($1,$2,$3)", user_id, -cost, f"army_recruit:{count}")
            return current + count, cost, balance


async def disband_soldiers(user_id: int, count: int) -> tuple[int, int]:
    if not isinstance(count, int) or count < 1:
        raise ValueError("تعداد سرباز برای مرخص‌کردن باید عددی مثبت باشد.")
    async with db().acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT soldiers FROM empire_armies WHERE telegram_id=$1 FOR UPDATE", user_id)
            if not row or int(row["soldiers"]) < count:
                raise ValueError("تعداد سربازان ارتش برای این کار کافی نیست.")
            remaining = int(row["soldiers"]) - count
            await conn.execute("UPDATE empire_armies SET soldiers=$2,updated_at=$3 WHERE telegram_id=$1", user_id, remaining, datetime.now(timezone.utc))
            return remaining, count


async def declare_war(user_id: int, attack_city_key: str, target_city_key: str):
    """Create a 10-minute pending war against another player's territory."""
    if attack_city_key not in CITIES or target_city_key not in CITIES:
        raise ValueError("کلید قلمرو نامعتبر است.")
    if attack_city_key == target_city_key:
        raise ValueError("قلمرو مهاجم و هدف باید متفاوت باشند.")
    async with db().acquire() as conn:
        async with conn.transaction():
            user = await conn.fetchrow("SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE", user_id)
            if not user:
                raise ValueError("ابتدا در خصوصی ربات /start را بزن.")
            # Lock city rows in sorted order to reduce lock-order deadlocks.
            keys = sorted([attack_city_key, target_city_key])
            locked = {}
            for key in keys:
                locked[key] = await conn.fetchrow("SELECT * FROM empire_cities WHERE city_key=$1 FOR UPDATE", key)
            attack_city, target_city = locked[attack_city_key], locked[target_city_key]
            if not attack_city or not target_city:
                raise ValueError("یکی از قلمروها پیدا نشد.")
            if attack_city['owner_id'] != user_id:
                raise ValueError("برای حمله باید مالک قلمرو مبدأ باشی.")
            if target_city['owner_id'] is None:
                raise ValueError("قلمرو آزاد را لازم نیست با جنگ بگیری؛ با /empire_city_buy بخر.")
            if target_city['owner_id'] == user_id:
                raise ValueError("نمی‌توانی به قلمرو خودت حمله کنی.")
            active_target_war = await conn.fetchval(
                "SELECT id FROM empire_wars WHERE target_city_key=$1 AND status='pending'", target_city_key
            )
            if active_target_war:
                raise ValueError(f"این قلمرو از قبل درگیر جنگ شمارهٔ {int(active_target_war)} است.")
            defender_id = int(target_city['owner_id'])
            alliance_pair = await conn.fetchrow("""SELECT am.alliance_id AS attacker_alliance, dm.alliance_id AS defender_alliance
                FROM (SELECT alliance_id FROM empire_alliance_members WHERE telegram_id=$1) am
                FULL OUTER JOIN (SELECT alliance_id FROM empire_alliance_members WHERE telegram_id=$2) dm ON TRUE""", user_id, defender_id)
            if alliance_pair and alliance_pair["attacker_alliance"] and alliance_pair["defender_alliance"]:
                attacker_alliance = int(alliance_pair["attacker_alliance"])
                defender_alliance = int(alliance_pair["defender_alliance"])
                if attacker_alliance == defender_alliance:
                    raise ValueError("نمی‌توانی به قلمرو هم‌اتحادی خودت حمله کنی.")
                pact_active = await conn.fetchval("""SELECT 1 FROM empire_alliance_pacts
                    WHERE status='active' AND expires_at>NOW()
                    AND alliance_a=LEAST($1,$2) AND alliance_b=GREATEST($1,$2) LIMIT 1""", attacker_alliance, defender_alliance)
                if pact_active:
                    raise ValueError("بین اتحاد شما و اتحاد هدف پیمان عدم تجاوز فعال است.")
            fee = war_fee(int(target_city['price']))
            if int(user['coins']) < fee:
                raise ValueError(f"هزینهٔ اعلام جنگ {fee} سکه است و موجودی کافی نیست.")
            count = await conn.fetchval("SELECT COUNT(*) FROM empire_cities WHERE owner_id=$1", user_id)
            roll = random.randint(0, 30)
            power = attack_power(int(count), int(attack_city['defense_level']), roll)
            army = await conn.fetchval("SELECT soldiers FROM empire_armies WHERE telegram_id=$1", user_id)
            power += army_power_bonus(int(army or 0))
            try:
                adv = await army_advanced.total_army_power(user_id)
                power += int(adv.get("unit_power") or 0) + int(adv.get("commander_power") or 0)
            except Exception:
                pass
            loadout = await conn.fetchrow("SELECT weapon_key,armor_key FROM empire_equipment_loadouts WHERE telegram_id=$1", user_id)
            if loadout:
                power += item_stats(loadout['weapon_key'], loadout['armor_key'])['attack']
            now = datetime.now(timezone.utc)
            resolves_at = now + timedelta(seconds=WAR_PREPARATION_SECONDS)
            balance = int(user['coins']) - fee
            await conn.execute("UPDATE users SET coins=$2 WHERE telegram_id=$1", user_id, balance)
            row = await conn.fetchrow("""INSERT INTO empire_wars(attacker_id,defender_id,attack_city_key,target_city_key,attack_power,fee,resolves_at)
                VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING id""", user_id, defender_id, attack_city_key, target_city_key, power, fee, resolves_at)
            await conn.execute("INSERT INTO empire_transactions(telegram_id,amount,reason) VALUES($1,$2,$3)", user_id, -fee, f"war_fee:{row['id']}:{target_city_key}")
            return int(row['id']), attack_city['name'], target_city['name'], fee, balance, resolves_at, defender_id, power


async def pending_wars(user_id: int | None = None):
    async with db().acquire() as conn:
        if user_id is None:
            return await conn.fetch("""SELECT w.*,a.name AS attack_city_name,t.name AS target_city_name,
                au.display_name AS attacker_name,du.display_name AS defender_name
                FROM empire_wars w JOIN empire_cities a ON a.city_key=w.attack_city_key
                JOIN empire_cities t ON t.city_key=w.target_city_key
                JOIN users au ON au.telegram_id=w.attacker_id JOIN users du ON du.telegram_id=w.defender_id
                WHERE w.status='pending' ORDER BY w.resolves_at""")
        return await conn.fetch("""SELECT w.*,a.name AS attack_city_name,t.name AS target_city_name,
            au.display_name AS attacker_name,du.display_name AS defender_name
            FROM empire_wars w JOIN empire_cities a ON a.city_key=w.attack_city_key
            JOIN empire_cities t ON t.city_key=w.target_city_key
            JOIN users au ON au.telegram_id=w.attacker_id JOIN users du ON du.telegram_id=w.defender_id
            WHERE w.status='pending' AND (w.attacker_id=$1 OR w.defender_id=$1) ORDER BY w.resolves_at""", user_id)


async def resolve_war(user_id: int, war_id: int):
    """Resolve a war after its preparation window; attacker or defender may trigger it."""
    async with db().acquire() as conn:
        async with conn.transaction():
            war = await conn.fetchrow("SELECT * FROM empire_wars WHERE id=$1 FOR UPDATE", war_id)
            if not war or war['status'] != 'pending':
                raise ValueError("جنگ فعال با این شناسه پیدا نشد یا قبلاً پایان یافته است.")
            if user_id not in (int(war['attacker_id']), int(war['defender_id'])):
                raise ValueError("فقط دو طرف جنگ می‌توانند نتیجه را نهایی کنند.")
            now = datetime.now(timezone.utc)
            if now < war['resolves_at']:
                remain = int((war['resolves_at'] - now).total_seconds())
                raise ValueError(f"نیروها هنوز در حال آماده‌سازی‌اند؛ {max(1, remain // 60)} دقیقهٔ دیگر نتیجه قابل تعیین است.")
            target = await conn.fetchrow("SELECT * FROM empire_cities WHERE city_key=$1 FOR UPDATE", war['target_city_key'])
            if not target or int(target['owner_id'] or 0) != int(war['defender_id']):
                await conn.execute("UPDATE empire_wars SET status='cancelled',resolved_at=$2 WHERE id=$1", war_id, now)
                return {"id": war_id, "cancelled": True, "won": False, "attack_power": int(war['attack_power']),
                        "defense_power": 0, "target_name": target['name'] if target else war['target_city_key'],
                        "attacker_id": int(war['attacker_id']), "defender_id": int(war['defender_id']),
                        "new_owner_id": int(target['owner_id']) if target and target['owner_id'] else None}
            defender_city_count = int(await conn.fetchval("SELECT COUNT(*) FROM empire_cities WHERE owner_id=$1", war['defender_id']))
            defense = defense_power(max(1, defender_city_count), int(target['defense_level'])) + random.randint(0, 15)
            defenders = await conn.fetchval("SELECT soldiers FROM empire_armies WHERE telegram_id=$1", war['defender_id'])
            defense += army_power_bonus(int(defenders or 0))
            attack = int(war['attack_power'])
            won = war_attacker_wins(attack, defense)
            if won:
                await conn.execute("UPDATE empire_cities SET owner_id=$2,last_tax_at=NULL,updated_at=$3 WHERE city_key=$1", war['target_city_key'], war['attacker_id'], now)
                status = 'attacker_won'
                await conn.execute("INSERT INTO empire_transactions(telegram_id,amount,reason) VALUES($1,0,$2)", int(war['attacker_id']), f"war_conquest:{war_id}:{war['target_city_key']}")
            else:
                status = 'defender_won'
            await conn.execute("UPDATE empire_wars SET status=$2,defense_power=$3,resolved_at=$4 WHERE id=$1", war_id, status, defense, now)
            return {"id": war_id, "won": won, "attack_power": attack, "defense_power": defense,
                    "target_name": target['name'], "attacker_id": int(war['attacker_id']),
                    "defender_id": int(war['defender_id']), "new_owner_id": int(war['attacker_id']) if won else int(war['defender_id'])}


async def resolve_expired_wars(limit: int = 20):
    """Automatically resolve expired wars. Safe against a simultaneous manual resolution."""
    if limit < 1 or limit > 100:
        raise ValueError("تعداد جنگ‌ها باید بین ۱ تا ۱۰۰ باشد.")
    async with db().acquire() as conn:
        ids = await conn.fetch("""SELECT id FROM empire_wars
            WHERE status='pending' AND resolves_at <= NOW()
            ORDER BY resolves_at, id LIMIT $1""", limit)
    results = []
    for item in ids:
        war_id = int(item['id'])
        async with db().acquire() as conn:
            async with conn.transaction():
                war = await conn.fetchrow("SELECT * FROM empire_wars WHERE id=$1 FOR UPDATE", war_id)
                if not war or war['status'] != 'pending' or war['resolves_at'] > datetime.now(timezone.utc):
                    continue
                now = datetime.now(timezone.utc)
                target = await conn.fetchrow("SELECT * FROM empire_cities WHERE city_key=$1 FOR UPDATE", war['target_city_key'])
                base = {"id": war_id, "attacker_id": int(war['attacker_id']),
                        "defender_id": int(war['defender_id']),
                        "target_name": target['name'] if target else war['target_city_key']}
                if not target or int(target['owner_id'] or 0) != int(war['defender_id']):
                    await conn.execute("UPDATE empire_wars SET status='cancelled',resolved_at=$2 WHERE id=$1", war_id, now)
                    results.append({**base, "cancelled": True, "won": False,
                                    "attack_power": int(war['attack_power']), "defense_power": 0})
                    continue
                defender_city_count = int(await conn.fetchval(
                    "SELECT COUNT(*) FROM empire_cities WHERE owner_id=$1", war['defender_id']))
                defense = defense_power(max(1, defender_city_count), int(target['defense_level'])) + random.randint(0, 15)
                defenders = await conn.fetchval("SELECT soldiers FROM empire_armies WHERE telegram_id=$1", war['defender_id'])
                defense += army_power_bonus(int(defenders or 0))
                loadout = await conn.fetchrow("SELECT weapon_key,armor_key FROM empire_equipment_loadouts WHERE telegram_id=$1", int(war['defender_id']))
                if loadout:
                    defense += item_stats(loadout['weapon_key'], loadout['armor_key'])['defense']
                attack = int(war['attack_power'])
                won = war_attacker_wins(attack, defense)
                if won:
                    await conn.execute("UPDATE empire_cities SET owner_id=$2,last_tax_at=NULL,updated_at=$3 WHERE city_key=$1",
                                       war['target_city_key'], war['attacker_id'], now)
                    status = 'attacker_won'
                    await conn.execute("INSERT INTO empire_transactions(telegram_id,amount,reason) VALUES($1,0,$2)",
                                       int(war['attacker_id']), f"war_conquest:{war_id}:{war['target_city_key']}")
                else:
                    status = 'defender_won'
                await conn.execute("UPDATE empire_wars SET status=$2,defense_power=$3,resolved_at=$4 WHERE id=$1",
                                   war_id, status, defense, now)
                results.append({**base, "cancelled": False, "won": won,
                                "attack_power": attack, "defense_power": defense})
    return results


async def war_history(user_id: int, limit: int = 20):
    """Return recent wars involving the player, including finished battles."""
    if not 1 <= limit <= 50:
        raise ValueError("تعداد تاریخچه باید بین ۱ تا ۵۰ باشد.")
    async with db().acquire() as conn:
        return await conn.fetch(
            """SELECT w.id,w.attacker_id,w.defender_id,w.attack_city_key,w.target_city_key,
                      w.attack_power,w.defense_power,w.status,w.fee,w.created_at,w.resolves_at,w.resolved_at,
                      a.name AS attack_city_name,t.name AS target_city_name,
                      au.display_name AS attacker_name,du.display_name AS defender_name
               FROM empire_wars w
               JOIN empire_cities a ON a.city_key=w.attack_city_key
               JOIN empire_cities t ON t.city_key=w.target_city_key
               JOIN users au ON au.telegram_id=w.attacker_id
               JOIN users du ON du.telegram_id=w.defender_id
               WHERE w.attacker_id=$1 OR w.defender_id=$1
               ORDER BY w.created_at DESC LIMIT $2""", user_id, limit)
