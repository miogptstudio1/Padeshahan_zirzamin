
"""انجمن مخفی — مدیریت ساده چند راند."""
from __future__ import annotations
import random
from games.minigames import rooms as R

ACTS = ['جذب عضو', 'مأموریت', 'توطئه']

async def start(room_id: int) -> dict:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["society"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['society']} نفر")
    scores = {str(int(p["telegram_id"])): 0 for p in pl}
    state = {"scores": scores, "round": 1, "max_rounds": 5, "actions": {}, "phase": "act"}
    await R.set_status(room_id, "playing", state)
    return state

async def act(room_id: int, uid: int, choice: str) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    if st.get("phase") != "act":
        raise ValueError("فاز عمل نیست")
    st.setdefault("actions", {})[str(uid)] = choice
    # امتیاز تصادفی وابسته به عمل
    gain = random.randint(1, 4)
    st["scores"][str(uid)] = int(st["scores"].get(str(uid), 0)) + gain
    await R.save_state(room_id, st)
    return {"gain": gain, "state": st}

async def next_round(room_id: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    rnd = int(st.get("round") or 1) + 1
    st["actions"] = {}
    if rnd > int(st.get("max_rounds") or 5):
        st["phase"] = "ended"
        best = max(st["scores"].items(), key=lambda x: int(x[1]))[0]
        st["winner_id"] = int(best)
        await R.set_status(room_id, "finished", st)
    else:
        st["round"] = rnd
        await R.save_state(room_id, st)
    return st
