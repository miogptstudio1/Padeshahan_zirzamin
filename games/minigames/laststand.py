
"""آخرین بازمانده — حذف مرحله‌ای با رأی."""
from __future__ import annotations
from collections import Counter
from typing import Any
from games.minigames import rooms as R


async def start(room_id: int) -> dict:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["laststand"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['laststand']} نفر")
    alive = {str(int(p["telegram_id"])): True for p in pl}
    state = {"alive": alive, "phase": "vote", "votes": {}, "round": 1}
    await R.set_status(room_id, "playing", state)
    return state


async def vote(room_id: int, uid: int, target: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    if not st.get("alive", {}).get(str(uid)):
        raise ValueError("حذف شدی")
    if not st.get("alive", {}).get(str(target)):
        raise ValueError("هدف زنده نیست")
    if int(uid) == int(target):
        raise ValueError("به خودت نمی‌تونی رأی بدی")
    st.setdefault("votes", {})[str(uid)] = int(target)
    await R.save_state(room_id, st)
    return st


async def resolve(room_id: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    votes = st.get("votes") or {}
    if not votes:
        raise ValueError("رأیی نیست")
    c = Counter(int(v) for v in votes.values())
    out, _ = c.most_common(1)[0]
    st["alive"][str(out)] = False
    st["votes"] = {}
    st["last_out"] = out
    alive = [int(u) for u, a in st["alive"].items() if a]
    if len(alive) <= 1:
        st["phase"] = "ended"
        st["winner_id"] = alive[0] if alive else None
        await R.set_status(room_id, "finished", st)
    else:
        st["round"] = int(st.get("round") or 1) + 1
        await R.save_state(room_id, st)
    return st
