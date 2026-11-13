
"""رمزگشا — شکستن رمز."""
from __future__ import annotations
import random
from games.minigames import rooms as R

CODES = [
    ("پادشاه", "حاکم زیرزمین"),
    ("خنجر", "سلاح پنهان"),
    ("سایه", "جایی که قایم می‌شی"),
    ("سکه", "پول کثیف"),
    ("قلعه", "سنگر"),
]

async def start(room_id: int) -> dict:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["decoder"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['decoder']} نفر")
    word, hint = random.choice(CODES)
    state = {"word": word, "hint": hint, "tries": 0, "max_tries": 8, "phase": "play", "solved_by": None}
    await R.set_status(room_id, "playing", state)
    return state

async def guess(room_id: int, uid: int, text: str) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    if st.get("phase") != "play":
        raise ValueError("تموم شده")
    st["tries"] = int(st.get("tries") or 0) + 1
    ok = (text or "").strip() == st["word"]
    if ok:
        st["phase"] = "ended"
        st["solved_by"] = int(uid)
        await R.set_status(room_id, "finished", st)
        return {"ok": True, "state": st}
    if st["tries"] >= int(st.get("max_tries") or 8):
        st["phase"] = "ended"
        await R.set_status(room_id, "finished", st)
        return {"ok": False, "fail": True, "state": st}
    await R.save_state(room_id, st)
    return {"ok": False, "tries": st["tries"], "hint": st["hint"], "state": st}
