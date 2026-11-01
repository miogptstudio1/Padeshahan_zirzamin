"""جاسوسی روی بازیکن‌ها — اطلاعات محدود با هزینه و شانس لو رفتن."""
from __future__ import annotations
import random
from datetime import datetime, timezone
from typing import Any

from core.database import db
from games.empire import service as empire_service
from games.empire import army_advanced
from games.empire import crime as crime_service
from games.reputation import service as rep_service

SPY_COST = 80
SPY_COOLDOWN = 15 * 60


async def spy_on(spy_id: int, target_id: int) -> dict[str, Any]:
    spy_id, target_id = int(spy_id), int(target_id)
    if spy_id == target_id:
        raise ValueError("روی خودت جاسوسی؟")
    async with db().acquire() as conn:
        last = await conn.fetchval(
            """SELECT created_at FROM spy_reports WHERE spy_id=$1
               ORDER BY id DESC LIMIT 1""",
            spy_id,
        )
        if last is not None:
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last).total_seconds()
            if elapsed < SPY_COOLDOWN:
                raise ValueError(f"جاسوس هنوز برگشته؛ {max(1, int(SPY_COOLDOWN-elapsed)//60)} دقیقه صبر کن.")

        coins = await conn.fetchval(
            "SELECT coins FROM users WHERE telegram_id=$1 FOR UPDATE", spy_id
        )
        if coins is None:
            raise ValueError("اول شروع را بزن.")
        if int(coins) < SPY_COST:
            raise ValueError(f"هزینه جاسوسی {SPY_COST} سکه است.")
        t = await conn.fetchrow(
            "SELECT display_name, coins FROM users WHERE telegram_id=$1", target_id
        )
        if not t:
            raise ValueError("هدف پیدا نشد.")
        await conn.execute(
            "UPDATE users SET coins = coins - $2 WHERE telegram_id=$1", spy_id, SPY_COST
        )

    # gather intel
    cities = await empire_service.my_cities(target_id)
    try:
        power = await army_advanced.total_army_power(target_id)
        total_p = int(power.get("total") or 0)
        soldiers = int(power.get("soldiers") or 0)
    except Exception:
        army = await empire_service.army_for(target_id)
        soldiers = int(army.get("soldiers") or 0)
        total_p = soldiers * 3
    try:
        hp = await crime_service.hp_status(target_id)
        hp_s = f"{hp['hp']}/{hp['max_hp']}"
    except Exception:
        hp_s = "?"

    success = random.random() < 0.75
    if success:
        city_names = "، ".join(c["name"] for c in cities[:5]) or "هیچ"
        report = (
            f"هدف: {t['display_name']}\n"
            f"سکه (تقریبی): حدود {max(0, int(t['coins']) + random.randint(-80, 80))}\n"
            f"سرباز: {soldiers} · قدرت حدودی: {total_p}\n"
            f"جان: {hp_s}\n"
            f"قلمروها ({len(cities)}): {city_names}"
        )
        exposed = False
    else:
        report = "جاسوس لو رفت. چیزی دستت نیومد."
        exposed = True
        # small fine already paid as cost; optional notify handled by caller

    async with db().acquire() as conn:
        await conn.execute(
            """INSERT INTO spy_reports(spy_id, target_id, success, report, cost)
               VALUES($1,$2,$3,$4,$5)""",
            spy_id,
            target_id,
            success,
            report,
            SPY_COST,
        )
        bal = await conn.fetchval("SELECT coins FROM users WHERE telegram_id=$1", spy_id)

    try:
        await rep_service.add(spy_id, -2 if success else -5)
        if success:
            await rep_service.add(target_id, 0)  # no-op keep target
    except Exception:
        pass
    return {
        "success": success,
        "exposed": exposed,
        "report": report,
        "cost": SPY_COST,
        "balance": int(bal),
        "target_name": t["display_name"],
        "target_id": target_id,
    }
