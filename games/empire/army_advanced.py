"""ارتش تخصصی و فرماندهان."""
from __future__ import annotations
from typing import Any

from core.database import db
from games.empire.army_rules import UNITS, COMMANDERS, UNIT_ALIASES, COMMANDER_ALIASES, unit_power
from games.empire import service as empire_service
from games.empire.engine import army_power_bonus


async def units_for(user_id: int) -> list[dict[str, Any]]:
    async with db().acquire() as conn:
        rows = await conn.fetch(
            "SELECT unit_key, quantity FROM empire_army_units WHERE telegram_id=$1 AND quantity>0",
            int(user_id),
        )
    out = []
    for r in rows:
        key = r["unit_key"]
        meta = UNITS.get(key, {})
        out.append({
            "key": key,
            "name": meta.get("name", key),
            "quantity": int(r["quantity"]),
            "power": unit_power(key, int(r["quantity"])),
            "cost": meta.get("cost"),
        })
    return out


async def commanders_for(user_id: int) -> list[dict[str, Any]]:
    async with db().acquire() as conn:
        rows = await conn.fetch(
            "SELECT commander_key, name, level FROM empire_commanders WHERE telegram_id=$1",
            int(user_id),
        )
    out = []
    for r in rows:
        key = r["commander_key"]
        meta = COMMANDERS.get(key, {})
        out.append({
            "key": key,
            "name": r["name"] or meta.get("name", key),
            "level": int(r["level"]),
            "bonus": int(meta.get("bonus_power", 0)),
            "desc": meta.get("desc", ""),
        })
    return out


async def total_army_power(user_id: int) -> dict[str, Any]:
    army = await empire_service.army_for(user_id)
    soldiers = int(army.get("soldiers") or 0)
    base = army_power_bonus(soldiers)
    units = await units_for(user_id)
    unit_p = sum(u["power"] for u in units)
    cmds = await commanders_for(user_id)
    cmd_p = sum(c["bonus"] for c in cmds)
    return {
        "soldiers": soldiers,
        "soldier_power": base,
        "units": units,
        "unit_power": unit_p,
        "commanders": cmds,
        "commander_power": cmd_p,
        "total": base + unit_p + cmd_p,
    }


async def recruit_unit(user_id: int, unit_key: str, count: int = 1) -> dict[str, Any]:
    user_id = int(user_id)
    count = int(count)
    if count < 1 or count > 50:
        raise ValueError("تعداد باید بین ۱ تا ۵۰ باشد.")
    key = UNIT_ALIASES.get(unit_key.lower().strip(), unit_key.lower().strip())
    if key not in UNITS:
        raise ValueError("واحد نامعتبر. یکی از: پیاده، کماندار، سواره، مهندس، سایه‌بان")
    meta = UNITS[key]
    cost = int(meta["cost"]) * count
    async with db().acquire() as conn:
        async with conn.transaction():
            coins = await conn.fetchval(
                "SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE", user_id
            )
            if coins is None:
                raise ValueError("اول شروع را بزن.")
            if int(coins) < cost:
                raise ValueError(f"سکه کافی نیست؛ هزینه {cost} است.")
            await conn.execute(
                "UPDATE users SET coins = coins - $2 WHERE telegram_id=$1", user_id, cost
            )
            await conn.execute(
                """INSERT INTO empire_army_units(telegram_id, unit_key, quantity)
                   VALUES($1,$2,$3)
                   ON CONFLICT(telegram_id, unit_key)
                   DO UPDATE SET quantity = empire_army_units.quantity + EXCLUDED.quantity""",
                user_id,
                key,
                count,
            )
            qty = await conn.fetchval(
                "SELECT quantity FROM empire_army_units WHERE telegram_id=$1 AND unit_key=$2",
                user_id,
                key,
            )
            bal = await conn.fetchval("SELECT coins FROM users WHERE telegram_id=$1", user_id)
    return {
        "unit": meta["name"],
        "key": key,
        "quantity": int(qty),
        "cost": cost,
        "balance": int(bal),
    }


async def hire_commander(user_id: int, commander_key: str) -> dict[str, Any]:
    user_id = int(user_id)
    key = COMMANDER_ALIASES.get(commander_key.lower().strip(), commander_key.lower().strip())
    if key not in COMMANDERS:
        raise ValueError("فرمانده نامعتبر. لیست: رضا، ندا، کاوه، شاهین")
    meta = COMMANDERS[key]
    cost = int(meta["cost"])
    async with db().acquire() as conn:
        async with conn.transaction():
            exists = await conn.fetchval(
                "SELECT 1 FROM empire_commanders WHERE telegram_id=$1 AND commander_key=$2",
                user_id,
                key,
            )
            if exists:
                raise ValueError("این فرمانده را قبلاً استخدام کرده‌ای.")
            coins = await conn.fetchval(
                "SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE", user_id
            )
            if coins is None:
                raise ValueError("اول شروع را بزن.")
            if int(coins) < cost:
                raise ValueError(f"سکه کافی نیست؛ هزینه {cost} است.")
            await conn.execute(
                "UPDATE users SET coins = coins - $2 WHERE telegram_id=$1", user_id, cost
            )
            await conn.execute(
                """INSERT INTO empire_commanders(telegram_id, commander_key, name)
                   VALUES($1,$2,$3)""",
                user_id,
                key,
                meta["name"],
            )
            bal = await conn.fetchval("SELECT coins FROM users WHERE telegram_id=$1", user_id)
    return {
        "commander": meta["name"],
        "bonus": meta["bonus_power"],
        "cost": cost,
        "balance": int(bal),
        "desc": meta["desc"],
    }


def catalog_text() -> str:
    lines = ["⚔️ <b>ارتش پیشرفته</b>\n", "<b>واحدها:</b>"]
    for k, m in UNITS.items():
        lines.append(f"• {m['name']} — {m['cost']}🪙 · قدرت {m['power']} — {m['desc']}")
        lines.append(f"  استخدام: <code>استخدام {m['name']}</code>")
    lines.append("\n<b>فرماندهان:</b>")
    for k, m in COMMANDERS.items():
        lines.append(f"• {m['name']} — {m['cost']}🪙 · {m['desc']}")
        lines.append(f"  استخدام: <code>فرمانده {m['name'].split()[0]}</code>")
    lines.append("\nوضعیت: <code>ارتش پیشرفته</code>")
    return "\n".join(lines)
