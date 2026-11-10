
"""بازی‌های سریع انفرادی."""
from __future__ import annotations
import random
from core.database import db

async def dice(user_id: int) -> dict:
    a, b = random.randint(1, 6), random.randint(1, 6)
    total = a + b
    reward = 0
    if total == 12:
        reward = 40
    elif total >= 10:
        reward = 15
    elif a == b:
        reward = 10
    if reward:
        async with db().acquire() as conn:
            await conn.execute(
                "UPDATE users SET coins = coins + $2 WHERE telegram_id=$1",
                int(user_id), reward,
            )
    return {"a": a, "b": b, "total": total, "reward": reward}


async def coin_flip(user_id: int, pick: str) -> dict:
    pick = {"شیر": "heads", "خط": "tails", "heads": "heads", "tails": "tails"}.get(
        (pick or "").strip().lower(), ""
    )
    if pick not in {"heads", "tails"}:
        raise ValueError("شیر یا خط؟")
    result = random.choice(["heads", "tails"])
    win = pick == result
    reward = 8 if win else 0
    if reward:
        async with db().acquire() as conn:
            await conn.execute(
                "UPDATE users SET coins = coins + $2 WHERE telegram_id=$1",
                int(user_id), reward,
            )
    return {
        "result": result,
        "result_fa": "شیر" if result == "heads" else "خط",
        "win": win,
        "reward": reward,
    }


async def duel_power(a_id: int, b_id: int) -> dict:
    from games.empire.crime import _power
    from games.gym import service as gym_service
    pa = await _power(a_id)
    pb = await _power(b_id)
    try:
        pa += int((await gym_service.combat_bonus(a_id)).get("power") or 0)
        pb += int((await gym_service.combat_bonus(b_id)).get("power") or 0)
    except Exception:
        pass
    # luck
    pa += random.randint(0, 15)
    pb += random.randint(0, 15)
    if pa == pb:
        winner = random.choice([a_id, b_id])
    else:
        winner = a_id if pa > pb else b_id
    return {"power_a": pa, "power_b": pb, "winner_id": winner}
