
"""اتاق فرار — معماهای گروهی با زمان محدود."""
from __future__ import annotations
import random
import time
from typing import Any

from games.minigames import rooms as R

PUZZLES = [
    {
        "q": "عدد بعدی چیست؟ ۲، ۳، ۵، ۷، ۱۱، ؟",
        "answers": {"13", "۱۳"},
        "hint": "اعداد اول",
    },
    {
        "q": "کلمه‌ای ۵ حرفی: خانه‌ی پادشاهان زیرزمین با «پ» شروع می‌شه.",
        "answers": {"پناهگاه", "پناه گاه"},
        "hint": "جایی که اول بازی می‌گیری",
    },
    {
        "q": "اگر ۳ سکه بدزدی و ۲ تا برگردونی، چند تا سود کردی؟",
        "answers": {"1", "۱", "یک"},
        "hint": "ساده حساب کن",
    },
    {
        "q": "رمز گاوصندوق: سال ساخت تلگرام (چهار رقم).",
        "answers": {"2013", "۲۰۱۳"},
        "hint": "حدود ۲۰۱۳",
    },
    {
        "q": "در کودتا برای کودتا چند سکه لازم است؟",
        "answers": {"7", "۷", "هفت"},
        "hint": "اقدام قطعی",
    },
    {
        "q": "چند حرف در کلمه‌ی «امپراتوری» است؟",
        "answers": {"9", "۹"},
        "hint": "بشمار",
    },
]


async def start(room_id: int) -> dict[str, Any]:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["escape"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['escape']} نفر.")
    pack = random.sample(PUZZLES, k=min(4, len(PUZZLES)))
    state = {
        "puzzles": pack,
        "index": 0,
        "solved": 0,
        "wrong": 0,
        "started_at": time.time(),
        "limit_sec": 8 * 60,
        "phase": "playing",
    }
    await R.set_status(room_id, "playing", state)
    return state


def current_puzzle(state: dict) -> dict | None:
    idx = int(state.get("index") or 0)
    pz = state.get("puzzles") or []
    if idx >= len(pz):
        return None
    return pz[idx]


async def answer(room_id: int, user_id: int, text: str) -> dict:
    r = await R.room(room_id)
    if not r or r["status"] != "playing":
        raise ValueError("بازی فعال نیست.")
    st = R.decode(r["state"])
    if time.time() - float(st.get("started_at") or 0) > int(st.get("limit_sec") or 480):
        st["phase"] = "failed"
        await R.set_status(room_id, "finished", st)
        return {"ok": False, "reason": "timeout", "solved": st.get("solved", 0)}
    pz = current_puzzle(st)
    if not pz:
        st["phase"] = "won"
        await R.set_status(room_id, "finished", st)
        return {"ok": True, "finished": True, "solved": st.get("solved", 0)}
    ans = (text or "").strip().lower().replace(" ", "")
    valid = {a.strip().lower().replace(" ", "") for a in pz["answers"]}
    if ans in valid:
        st["index"] = int(st["index"]) + 1
        st["solved"] = int(st.get("solved") or 0) + 1
        if st["index"] >= len(st["puzzles"]):
            st["phase"] = "won"
            await R.set_status(room_id, "finished", st)
            return {"ok": True, "finished": True, "solved": st["solved"], "next": None}
        await R.save_state(room_id, st)
        return {"ok": True, "finished": False, "solved": st["solved"], "next": current_puzzle(st)}
    st["wrong"] = int(st.get("wrong") or 0) + 1
    await R.save_state(room_id, st)
    return {"ok": False, "reason": "wrong", "hint": pz.get("hint"), "wrong": st["wrong"]}
