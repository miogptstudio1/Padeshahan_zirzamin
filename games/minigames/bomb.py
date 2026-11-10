
"""بمب ساعتی — سیب‌زمینی داغ."""
from __future__ import annotations
import random
from typing import Any
from games.minigames import rooms as R


async def start(room_id: int) -> dict:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["bomb"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['bomb']} نفر")
    ids = [int(p["telegram_id"]) for p in pl]
    holder = random.choice(ids)
    state = {
        "alive": {str(i): True for i in ids},
        "holder": holder,
        "ticks": 0,
        "explode_at": random.randint(4, 9),
        "phase": "pass",
    }
    await R.set_status(room_id, "playing", state)
    return state


async def pass_bomb(room_id: int, uid: int, target: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    if st.get("phase") != "pass":
        raise ValueError("بازی تموم شده")
    if int(uid) != int(st.get("holder") or 0):
        raise ValueError("بمب دست تو نیست")
    if not st.get("alive", {}).get(str(target)):
        raise ValueError("هدف حذف شده")
    if int(target) == int(uid):
        raise ValueError("به خودت نمی‌تونی پاس بدی")
    st["holder"] = int(target)
    st["ticks"] = int(st.get("ticks") or 0) + 1
    exploded = st["ticks"] >= int(st.get("explode_at") or 6)
    if exploded:
        st["alive"][str(target)] = False
        st["last_boom"] = int(target)
        alive = [int(u) for u, a in st["alive"].items() if a]
        if len(alive) <= 1:
            st["phase"] = "ended"
            st["winner_id"] = alive[0] if alive else None
            await R.set_status(room_id, "finished", st)
        else:
            st["holder"] = random.choice(alive)
            st["ticks"] = 0
            st["explode_at"] = random.randint(3, 8)
            await R.save_state(room_id, st)
        st["exploded"] = True
    else:
        st["exploded"] = False
        await R.save_state(room_id, st)
    return st
