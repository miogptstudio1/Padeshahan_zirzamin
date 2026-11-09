from __future__ import annotations
import asyncpg
from core.database import db

async def _ensure_upgrade_col(conn):
    try:
        await conn.execute(
            "ALTER TABLE empire_equipment_inventory ADD COLUMN IF NOT EXISTS upgrade_level INTEGER NOT NULL DEFAULT 0"
        )
    except Exception:
        pass

from games.empire.equipment_rules import ITEMS, BOX_PRICE, item_stats, roll_box_reward, upgraded_item_stats


def _item_view(key: str, quantity: int = 0) -> dict:
    item = ITEMS[key]
    return {"key": key, **item, "quantity": int(quantity)}


async def dashboard(user_id: int) -> dict:
    async with db().acquire() as conn:
        await _ensure_upgrade_col(conn)
        rows = await conn.fetch(
            "SELECT item_key,quantity,COALESCE(upgrade_level,0) AS upgrade_level FROM empire_equipment_inventory WHERE telegram_id=$1 AND quantity>0 ORDER BY item_key",
            user_id,
        )
        loadout = await conn.fetchrow("SELECT weapon_key,armor_key FROM empire_equipment_loadouts WHERE telegram_id=$1", user_id)
    inventory = []
    levels = {}
    for r in rows:
        if r['item_key'] not in ITEMS:
            continue
        lv = int(r['upgrade_level'] or 0)
        levels[r['item_key']] = lv
        view = _item_view(r['item_key'], r['quantity'])
        view['upgrade_level'] = lv
        st = upgraded_item_stats(
            r['item_key'] if ITEMS[r['item_key']].get('kind') == 'weapon' else None,
            lv if ITEMS[r['item_key']].get('kind') == 'weapon' else 0,
            r['item_key'] if ITEMS[r['item_key']].get('kind') == 'armor' else None,
            lv if ITEMS[r['item_key']].get('kind') == 'armor' else 0,
        )
        view['attack'] = st['attack'] if ITEMS[r['item_key']].get('kind') == 'weapon' else view.get('attack', 0)
        view['defense'] = st['defense'] if ITEMS[r['item_key']].get('kind') == 'armor' else view.get('defense', 0)
        inventory.append(view)
    weapon = loadout['weapon_key'] if loadout else None
    armor = loadout['armor_key'] if loadout else None
    w_lv = levels.get(weapon or '', 0)
    a_lv = levels.get(armor or '', 0)
    return {
        "catalog": [_item_view(k) for k in ITEMS],
        "shop": [_item_view(k) for k in ITEMS],
        "inventory": inventory,
        "equipped": {"weapon": weapon, "armor": armor},
        "stats": upgraded_item_stats(weapon, w_lv, armor, a_lv),
        "box_price": BOX_PRICE,
    }


async def buy(user_id: int, item_key: str, quantity: int = 1) -> dict:
    if item_key not in ITEMS:
        raise ValueError("این وسیله در فروشگاه وجود ندارد.")
    if not 1 <= quantity <= 10:
        raise ValueError("تعداد خرید باید بین ۱ تا ۱۰ باشد.")
    item = ITEMS[item_key]; cost = int(item['price']) * quantity
    async with db().acquire() as conn:
        async with conn.transaction():
            user = await conn.fetchrow("SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE", user_id)
            if not user:
                raise ValueError("ابتدا ربات را راه‌اندازی کن.")
            if int(user['coins']) < cost:
                raise ValueError(f"سکه کافی نیست؛ برای این خرید {cost} سکه لازم است.")
            await conn.execute("UPDATE users SET coins=coins-$2 WHERE telegram_id=$1", user_id, cost)
            await conn.execute("INSERT INTO empire_equipment_inventory(telegram_id,item_key,quantity) VALUES($1,$2,$3) ON CONFLICT(telegram_id,item_key) DO UPDATE SET quantity=empire_equipment_inventory.quantity+EXCLUDED.quantity,updated_at=NOW()", user_id, item_key, quantity)
            await conn.execute("INSERT INTO empire_equipment_transactions(telegram_id,item_key,quantity,total_cost,kind) VALUES($1,$2,$3,$4,'purchase')", user_id, item_key, quantity, cost)
            balance = int(await conn.fetchval("SELECT coins FROM users WHERE telegram_id=$1", user_id))
    return {"ok": True, "item": item['name'], "quantity": quantity, "cost": cost, "coins": balance}


async def equip(user_id: int, item_key: str) -> dict:
    item = ITEMS.get(item_key)
    if not item:
        raise ValueError("وسیلهٔ انتخاب‌شده معتبر نیست.")
    async with db().acquire() as conn:
        async with conn.transaction():
            quantity = await conn.fetchval("SELECT quantity FROM empire_equipment_inventory WHERE telegram_id=$1 AND item_key=$2 FOR UPDATE", user_id, item_key)
            if not quantity or int(quantity) < 1:
                raise ValueError("این وسیله را در موجودی نداری.")
            col = 'weapon_key' if item['kind'] == 'weapon' else 'armor_key'
            await conn.execute("INSERT INTO empire_equipment_loadouts(telegram_id,weapon_key,armor_key) VALUES($1,$2,$3) ON CONFLICT(telegram_id) DO NOTHING", user_id, item_key if col == 'weapon_key' else None, item_key if col == 'armor_key' else None)
            await conn.execute(f"UPDATE empire_equipment_loadouts SET {col}=$2,updated_at=NOW() WHERE telegram_id=$1", user_id, item_key)
            loadout = await conn.fetchrow("SELECT weapon_key,armor_key FROM empire_equipment_loadouts WHERE telegram_id=$1", user_id)
    return {"ok": True, "item": item['name'], "stats": item_stats(loadout['weapon_key'], loadout['armor_key'])}


async def open_box(user_id: int, request_id: str) -> dict:
    request_id = request_id.strip()
    if not 8 <= len(request_id) <= 80:
        raise ValueError("شناسهٔ درخواست نامعتبر است؛ دوباره تلاش کن.")
    async with db().acquire() as conn:
        async with conn.transaction():
            previous = await conn.fetchrow("SELECT reward_key,reward_amount FROM empire_equipment_box_claims WHERE telegram_id=$1 AND request_id=$2", user_id, request_id)
            if previous:
                key = previous['reward_key']; amount = int(previous['reward_amount'])
                if key in ITEMS:
                    return {"ok": True, "duplicate": True, "reward": {"type": "item", "key": key, "name": ITEMS[key]['name'], "amount": amount}, "coins": int(await conn.fetchval("SELECT coins FROM users WHERE telegram_id=$1", user_id))}
                return {"ok": True, "duplicate": True, "reward": {"type": "coins", "key": key, "amount": amount}, "coins": int(await conn.fetchval("SELECT coins FROM users WHERE telegram_id=$1", user_id))}
            user = await conn.fetchrow("SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE", user_id)
            if not user:
                raise ValueError("ابتدا ربات را راه‌اندازی کن.")
            if int(user['coins']) < BOX_PRICE:
                raise ValueError(f"برای باز کردن صندوق {BOX_PRICE} سکه لازم است.")
            reward = roll_box_reward()
            await conn.execute("UPDATE users SET coins=coins-$2 WHERE telegram_id=$1", user_id, BOX_PRICE)
            if reward['type'] == 'coins':
                await conn.execute("UPDATE users SET coins=coins+$2 WHERE telegram_id=$1", user_id, reward['amount'])
            else:
                await conn.execute("INSERT INTO empire_equipment_inventory(telegram_id,item_key,quantity) VALUES($1,$2,1) ON CONFLICT(telegram_id,item_key) DO UPDATE SET quantity=empire_equipment_inventory.quantity+1,updated_at=NOW()", user_id, reward['item_key'])
            await conn.execute("INSERT INTO empire_equipment_box_claims(telegram_id,request_id,reward_key,reward_amount) VALUES($1,$2,$3,$4)", user_id, request_id, reward['key'], reward['amount'])
            await conn.execute("INSERT INTO empire_equipment_transactions(telegram_id,item_key,quantity,total_cost,kind) VALUES($1,$2,1,$3,'box')", user_id, reward['key'], BOX_PRICE)
            balance = int(await conn.fetchval("SELECT coins FROM users WHERE telegram_id=$1", user_id))
    if reward['type'] == 'item':
        reward['name'] = ITEMS[reward['item_key']]['name']
    return {"ok": True, "duplicate": False, "reward": reward, "coins": balance}


async def combat_stats(user_id: int, conn: asyncpg.Connection | None = None) -> dict[str, int]:
    async def _load(c):
        await _ensure_upgrade_col(c)
        row = await c.fetchrow(
            "SELECT weapon_key,armor_key FROM empire_equipment_loadouts WHERE telegram_id=$1",
            user_id,
        )
        if not row:
            return {"attack": 0, "defense": 0}
        w_lv = 0
        a_lv = 0
        if row["weapon_key"]:
            w_lv = int(await c.fetchval(
                "SELECT COALESCE(upgrade_level,0) FROM empire_equipment_inventory WHERE telegram_id=$1 AND item_key=$2",
                user_id, row["weapon_key"],
            ) or 0)
        if row["armor_key"]:
            a_lv = int(await c.fetchval(
                "SELECT COALESCE(upgrade_level,0) FROM empire_equipment_inventory WHERE telegram_id=$1 AND item_key=$2",
                user_id, row["armor_key"],
            ) or 0)
        return upgraded_item_stats(row["weapon_key"], w_lv, row["armor_key"], a_lv)

    if conn is not None:
        return await _load(conn)
    async with db().acquire() as acquired:
        return await _load(acquired)




def upgrade_cost(item_key: str, level: int) -> int:
    base = int(ITEMS.get(item_key, {}).get("price") or 200)
    lv = max(0, int(level))
    return max(50, int(base * 0.25) + lv * 80 + lv * lv * 15)


async def upgrade_item(user_id: int, item_key: str) -> dict:
    """ارتقای سطح تجهیزات مالک‌شده."""
    user_id = int(user_id)
    item_key = (item_key or "").strip().lower()
    if item_key not in ITEMS:
        # try by name
        for k, v in ITEMS.items():
            if v.get("name") == item_key or k == item_key:
                item_key = k
                break
    if item_key not in ITEMS:
        raise ValueError("این وسیله تو فروشگاه نیست.")
    async with db().acquire() as conn:
        await _ensure_upgrade_col(conn)
        async with conn.transaction():
            row = await conn.fetchrow(
                """SELECT quantity, COALESCE(upgrade_level,0) AS upgrade_level
                   FROM empire_equipment_inventory
                   WHERE telegram_id=$1 AND item_key=$2 FOR UPDATE""",
                user_id, item_key,
            )
            if not row or int(row["quantity"] or 0) < 1:
                raise ValueError("این وسیله رو نداری.")
            lv = int(row["upgrade_level"] or 0)
            if lv >= 10:
                raise ValueError("این وسیله به سقف ارتقا (+10) رسیده.")
            cost = upgrade_cost(item_key, lv)
            coins = int(await conn.fetchval(
                "SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE", user_id
            ) or 0)
            if coins < cost:
                raise ValueError(f"سکه کم است. لازم: {cost}")
            await conn.execute(
                "UPDATE users SET coins = coins - $2 WHERE telegram_id=$1", user_id, cost
            )
            await conn.execute(
                """UPDATE empire_equipment_inventory
                   SET upgrade_level=$3, updated_at=NOW()
                   WHERE telegram_id=$1 AND item_key=$2""",
                user_id, item_key, lv + 1,
            )
            bal = int(await conn.fetchval(
                "SELECT coins FROM users WHERE telegram_id=$1", user_id
            ) or 0)
    meta = ITEMS[item_key]
    stats = upgraded_item_stats(item_key, lv + 1)
    return {
        "item_key": item_key,
        "name": meta.get("name", item_key),
        "level": lv + 1,
        "cost": cost,
        "balance": bal,
        "attack": stats["attack"],
        "defense": stats["defense"],
        "next_cost": upgrade_cost(item_key, lv + 1) if lv + 1 < 10 else None,
    }
