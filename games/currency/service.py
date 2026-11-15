
"""ارزهای چندلایه: سکه → الماس → مینت (مول) → نوا."""
from __future__ import annotations
from typing import Any

from core.database import db

COINS_PER_DIAMOND = 1_000_000
DIAMONDS_PER_MINT = 1_000_000
MINTS_PER_NOVA = 1_000_000


async def ensure_columns(conn) -> None:
    for col in (
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS diamonds BIGINT NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS mint_mols BIGINT NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS novas BIGINT NOT NULL DEFAULT 0",
    ):
        try:
            await conn.execute(col)
        except Exception:
            pass


async def balances(user_id: int) -> dict[str, int]:
    async with db().acquire() as conn:
        await ensure_columns(conn)
        row = await conn.fetchrow(
            """SELECT COALESCE(coins,0) AS coins,
                      COALESCE(diamonds,0) AS diamonds,
                      COALESCE(mint_mols,0) AS mint_mols,
                      COALESCE(novas,0) AS novas
               FROM users WHERE telegram_id=$1""",
            int(user_id),
        )
    if not row:
        return {"coins": 0, "diamonds": 0, "mint_mols": 0, "novas": 0}
    return {
        "coins": int(row["coins"]),
        "diamonds": int(row["diamonds"]),
        "mint_mols": int(row["mint_mols"]),
        "novas": int(row["novas"]),
    }


def format_wallet(b: dict[str, int]) -> str:
    return (
        f"🪙 سکه: {b.get('coins', 0):,}\n"
        f"💎 الماس: {b.get('diamonds', 0):,}\n"
        f"⚛️ مینت: {b.get('mint_mols', 0):,} مول\n"
        f"🌟 نوا: {b.get('novas', 0):,}"
    )


def rates_text() -> str:
    return (
        "💱 نرخ تبدیل\n"
        f"۱ 💎 الماس = {COINS_PER_DIAMOND:,} 🪙 سکه\n"
        f"۱ ⚛️ مول مینت = {DIAMONDS_PER_MINT:,} 💎 الماس\n"
        f"۱ 🌟 نوا = {MINTS_PER_NOVA:,} ⚛️ مول مینت\n\n"
        "تبدیل الماس ۱\n"
        "تبدیل مینت ۱\n"
        "تبدیل نوا ۱\n"
        "تبدیل الماس به سکه ۱\n"
        "تبدیل مینت به الماس ۱\n"
        "تبدیل نوا به مینت ۱"
    )


async def convert(user_id: int, direction: str, amount: int) -> dict[str, Any]:
    amount = int(amount)
    if amount < 1:
        raise ValueError("تعداد باید حداقل ۱ باشد.")
    user_id = int(user_id)
    async with db().acquire() as conn:
        await ensure_columns(conn)
        async with conn.transaction():
            row = await conn.fetchrow(
                """SELECT COALESCE(coins,0) AS coins,
                          COALESCE(diamonds,0) AS diamonds,
                          COALESCE(mint_mols,0) AS mint_mols,
                          COALESCE(novas,0) AS novas
                   FROM users WHERE telegram_id=$1 FOR UPDATE""",
                user_id,
            )
            if not row:
                raise ValueError("اول شروع را بزن.")
            coins = int(row["coins"])
            diamonds = int(row["diamonds"])
            mint = int(row["mint_mols"])
            novas = int(row["novas"])
            d = direction.lower().strip()

            if d in {"diamond_from_coins", "سکه_به_الماس", "coins_to_diamond"}:
                need = amount * COINS_PER_DIAMOND
                if coins < need:
                    raise ValueError(f"سکه کم است. لازم: {need:,}")
                coins -= need
                diamonds += amount
                msg = f"{amount:,} 💎 الماس از {need:,} 🪙 سکه"

            elif d in {"coins_from_diamond", "الماس_به_سکه", "diamond_to_coins"}:
                if diamonds < amount:
                    raise ValueError("الماس کافی نیست.")
                diamonds -= amount
                gain = amount * COINS_PER_DIAMOND
                coins += gain
                msg = f"{amount:,} 💎 → {gain:,} 🪙 سکه"

            elif d in {"mint_from_diamond", "الماس_به_مینت", "diamond_to_mint"}:
                need = amount * DIAMONDS_PER_MINT
                if diamonds < need:
                    raise ValueError(f"الماس کم است. لازم: {need:,}")
                diamonds -= need
                mint += amount
                msg = f"{amount:,} ⚛️ مول مینت از {need:,} 💎"

            elif d in {"diamond_from_mint", "مینت_به_الماس", "mint_to_diamond"}:
                if mint < amount:
                    raise ValueError("مینت کافی نیست.")
                mint -= amount
                gain = amount * DIAMONDS_PER_MINT
                diamonds += gain
                msg = f"{amount:,} ⚛️ مول → {gain:,} 💎"

            elif d in {"nova_from_mint", "مینت_به_نوا", "mint_to_nova"}:
                need = amount * MINTS_PER_NOVA
                if mint < need:
                    raise ValueError(f"مینت کم است. لازم: {need:,} مول")
                mint -= need
                novas += amount
                msg = f"{amount:,} 🌟 نوا از {need:,} ⚛️ مول مینت"

            elif d in {"mint_from_nova", "نوا_به_مینت", "nova_to_mint"}:
                if novas < amount:
                    raise ValueError("نوا کافی نیست.")
                novas -= amount
                gain = amount * MINTS_PER_NOVA
                mint += gain
                msg = f"{amount:,} 🌟 → {gain:,} ⚛️ مول مینت"

            else:
                raise ValueError("مسیر تبدیل نامعتبر. بزن: نرخ")

            await conn.execute(
                """UPDATE users SET coins=$2, diamonds=$3, mint_mols=$4, novas=$5
                   WHERE telegram_id=$1""",
                user_id, coins, diamonds, mint, novas,
            )
    return {
        "message": msg,
        "coins": coins,
        "diamonds": diamonds,
        "mint_mols": mint,
        "novas": novas,
    }


async def admin_set(user_id: int, field: str, amount: int) -> dict[str, int]:
    field = field.lower()
    col = {
        "coins": "coins",
        "سکه": "coins",
        "diamonds": "diamonds",
        "الماس": "diamonds",
        "mint": "mint_mols",
        "مینت": "mint_mols",
        "nova": "novas",
        "نوا": "novas",
    }.get(field)
    if not col:
        raise ValueError("فیلد: سکه · الماس · مینت · نوا")
    amount = int(amount)
    if amount < 0:
        raise ValueError("منفی مجاز نیست")
    async with db().acquire() as conn:
        await ensure_columns(conn)
        await conn.execute(
            f"UPDATE users SET {col}=$2 WHERE telegram_id=$1",
            int(user_id), amount,
        )
    return await balances(user_id)
