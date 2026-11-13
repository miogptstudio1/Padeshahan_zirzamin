
"""حافظه طلایی — دنباله اعداد."""
from __future__ import annotations
import random
from games.minigames import rooms as R

async def start(room_id: int) -> dict:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["memory"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['memory']} نفر")
    seq = [random.randint(1, 9) for _ in range(4)]
    state = {"seq": seq, "level": 1, "phase": "show", "scores": {}}
    await R.set_status(room_id, "playing", state)
    return state

async def answer(room_id: int, uid: int, text: str) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    digits = "".join(ch for ch in (text or "") if ch.isdigit())
    expected = "".join(str(x) for x in st.get("seq") or [])
    if digits == expected:
        st["scores"][str(uid)] = int(st.get("scores", {}).get(str(uid), 0)) + 1
        lvl = int(st.get("level") or 1) + 1
        st["level"] = lvl
        st["seq"] = [random.randint(1, 9) for _ in range(3 + lvl)]
        if lvl > 5:
            st["phase"] = "ended"
            best = max(st["scores"].items(), key=lambda x: int(x[1]))[0]
            st["winner_id"] = int(best)
            await R.set_status(room_id, "finished", st)
            return {"ok": True, "done": True, "state": st}
        await R.save_state(room_id, st)
        return {"ok": True, "done": False, "state": st}
    st["phase"] = "ended"
    if st.get("scores"):
        best = max(st["scores"].items(), key=lambda x: int(x[1]))[0]
        st["winner_id"] = int(best)
    await R.set_status(room_id, "finished", st)
    return {"ok": False, "done": True, "state": st}
