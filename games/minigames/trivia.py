
"""نبرد دانایی — سؤال عمومی."""
from __future__ import annotations
import random
from games.minigames import rooms as R

QS = [
    ("پایتخت فرانسه؟", ["پاریس", "paris"]),
    ("۲×۸؟", ["16", "۱۶"]),
    ("رنگ پرچم ایران چندتاست؟", ["3", "۳", "سه"]),
    ("سازنده تلگرام؟", ["پاول دوروف", "دوروف", "durov"]),
    ("۵+۷؟", ["12", "۱۲"]),
]

async def start(room_id: int) -> dict:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["trivia"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['trivia']} نفر")
    q, ans = random.choice(QS)
    state = {"q": q, "ans": ans, "scores": {}, "round": 1, "max_rounds": 5, "phase": "ask"}
    await R.set_status(room_id, "playing", state)
    return state

async def answer(room_id: int, uid: int, text: str) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    if st.get("phase") != "ask":
        raise ValueError("سؤال فعال نیست")
    t = (text or "").strip().lower()
    ok = t in [a.lower() for a in st.get("ans") or []]
    if ok:
        st["scores"][str(uid)] = int(st.get("scores", {}).get(str(uid), 0)) + 1
        rnd = int(st.get("round") or 1) + 1
        if rnd > int(st.get("max_rounds") or 5):
            st["phase"] = "ended"
            best = max(st["scores"].items(), key=lambda x: int(x[1]))[0]
            st["winner_id"] = int(best)
            await R.set_status(room_id, "finished", st)
            return {"ok": True, "done": True, "state": st}
        q, ans = random.choice(QS)
        st["q"], st["ans"], st["round"] = q, ans, rnd
        await R.save_state(room_id, st)
        return {"ok": True, "done": False, "state": st}
    return {"ok": False, "done": False, "state": st}
