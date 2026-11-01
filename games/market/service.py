"""بازار بازیکن‌به‌بازیکن — فروش تجهیزات."""
from __future__ import annotations
from typing import Any

from core.database import db
from games.empire.equipment_rules import ITEMS


async def list_open(limit: int = 20) -> list[dict[str, Any]]:
    async with db().acquire() as conn:
        rows = await conn.fetch(
            """SELECT m.id, m.seller_id, m.item_key, m.quantity, m.price, m.created_at,
                      COALESCE(u.display_name, u.username, '') AS seller_name
               FROM market_listings m
               LEFT JOIN users u ON u.telegram_id = m.seller_id
               WHERE m.status='open'
               ORDER BY m.id DESC LIMIT $1""",
            limit,
        )
    out = []
    for r in rows:
        key = r["item_key"]
        out.append({
            "id": int(r["id"]),
            "seller_id": int(r["seller_id"]),
            "seller_name": r["seller_name"],
            "item_key": key,
            "item_name": ITEMS.get(key, {}).get("name", key),
            "quantity": int(r["quantity"]),
            "price": int(r["price"]),
        })
    return out


async def create_listing(seller_id: int, item_key: str, price: int, quantity: int = 1) -> dict[str, Any]:
    seller_id = int(seller_id)
    price = int(price)
    quantity = int(quantity)
    if item_key not in ITEMS:
        raise ValueError("آیتم نامعتبر است.")
    if price < 1 or price > 1_000_000:
        raise ValueError("قیمت نامعتبر است.")
    if quantity < 1 or quantity > 20:
        raise ValueError("تعداد نامعتبر است.")
    async with db().acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """SELECT quantity FROM empire_equipment_inventory
                   WHERE telegram_id=$1 AND item_key=$2 FOR UPDATE""",
                seller_id,
                item_key,
            )
            if not row or int(row["quantity"]) < quantity:
                raise ValueError("این آیتم را به اندازه کافی در موجودی نداری.")
            # unequip if needed
            load = await conn.fetchrow(
                "SELECT weapon_key, armor_key FROM empire_equipment_loadouts WHERE telegram_id=$1",
                seller_id,
            )
            if load and (load["weapon_key"] == item_key or load["armor_key"] == item_key):
                if int(row["quantity"]) <= quantity:
                    raise ValueError("اول آیتم مجهز را از حالت تجهیز خارج کن یا بیشتر از یکی داشته باش.")
            new_q = int(row["quantity"]) - quantity
            if new_q == 0:
                await conn.execute(
                    "DELETE FROM empire_equipment_inventory WHERE telegram_id=$1 AND item_key=$2",
                    seller_id,
                    item_key,
                )
            else:
                await conn.execute(
                    "UPDATE empire_equipment_inventory SET quantity=$3 WHERE telegram_id=$1 AND item_key=$2",
                    seller_id,
                    item_key,
                    new_q,
                )
            lid = await conn.fetchval(
                """INSERT INTO market_listings(seller_id, item_key, quantity, price)
                   VALUES($1,$2,$3,$4) RETURNING id""",
                seller_id,
                item_key,
                quantity,
                price,
            )
    return {
        "id": int(lid),
        "item": ITEMS[item_key]["name"],
        "quantity": quantity,
        "price": price,
    }


async def buy_listing(buyer_id: int, listing_id: int) -> dict[str, Any]:
    buyer_id = int(buyer_id)
    listing_id = int(listing_id)
    async with db().acquire() as conn:
        async with conn.transaction():
            m = await conn.fetchrow(
                "SELECT * FROM market_listings WHERE id=$1 FOR UPDATE", listing_id
            )
            if not m or m["status"] != "open":
                raise ValueError("این آگهی موجود نیست.")
            if int(m["seller_id"]) == buyer_id:
                raise ValueError("نمی‌توانی آگهی خودت را بخری.")
            price = int(m["price"])
            coins = await conn.fetchval(
                "SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE", buyer_id
            )
            if coins is None:
                raise ValueError("اول شروع را بزن.")
            if int(coins) < price:
                raise ValueError("سکه کافی نیست.")
            # lock seller
            await conn.fetchval(
                "SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE", m["seller_id"]
            )
            await conn.execute(
                "UPDATE users SET coins = coins - $2 WHERE telegram_id=$1", buyer_id, price
            )
            await conn.execute(
                "UPDATE users SET coins = coins + $2 WHERE telegram_id=$1", m["seller_id"], price
            )
            await conn.execute(
                """INSERT INTO empire_equipment_inventory(telegram_id, item_key, quantity)
                   VALUES($1,$2,$3)
                   ON CONFLICT(telegram_id, item_key)
                   DO UPDATE SET quantity = empire_equipment_inventory.quantity + EXCLUDED.quantity""",
                buyer_id,
                m["item_key"],
                int(m["quantity"]),
            )
            await conn.execute(
                """UPDATE market_listings
                   SET status='sold', buyer_id=$2, closed_at=NOW() WHERE id=$1""",
                listing_id,
                buyer_id,
            )
            bal = await conn.fetchval("SELECT coins FROM users WHERE telegram_id=$1", buyer_id)
    return {
        "item": ITEMS.get(m["item_key"], {}).get("name", m["item_key"]),
        "price": price,
        "quantity": int(m["quantity"]),
        "balance": int(bal),
        "seller_id": int(m["seller_id"]),
    }


async def cancel_listing(seller_id: int, listing_id: int) -> None:
    seller_id = int(seller_id)
    listing_id = int(listing_id)
    async with db().acquire() as conn:
        async with conn.transaction():
            m = await conn.fetchrow(
                "SELECT * FROM market_listings WHERE id=$1 FOR UPDATE", listing_id
            )
            if not m or m["status"] != "open":
                raise ValueError("آگهی پیدا نشد.")
            if int(m["seller_id"]) != seller_id:
                raise ValueError("این آگهی مال تو نیست.")
            await conn.execute(
                """INSERT INTO empire_equipment_inventory(telegram_id, item_key, quantity)
                   VALUES($1,$2,$3)
                   ON CONFLICT(telegram_id, item_key)
                   DO UPDATE SET quantity = empire_equipment_inventory.quantity + EXCLUDED.quantity""",
                seller_id,
                m["item_key"],
                int(m["quantity"]),
            )
            await conn.execute(
                "UPDATE market_listings SET status='cancelled', closed_at=NOW() WHERE id=$1",
                listing_id,
            )
