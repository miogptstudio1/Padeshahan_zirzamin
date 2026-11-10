
"""شکار گنج — حدس مکان با سرنخ."""
from __future__ import annotations
import random
from typing import Any
from games.minigames import rooms as R

SPOTS = [
    ("اسکله متروکه", ["بوی نمک", "چوب پوسیده", "مه صبحگاهی"]),
    ("انبار زیر کاخ", ["بوی شراب", "سنگ سرد", "پژواک پا"]),
    ("بازار سیاه", ["هیاهو", "دود عود", "سکه‌های تقلبی"]),
    ("قبرستان قدیمی", ["سکوت", "شمع خاموش", "خاک خیس"]),
    ("برج مراقبت", ["باد تند", "چشم‌انداز شهر", "زنگ زنگ‌زده"]),
]


async def start(room_id: int) -> dict:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["treasure"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['treasure']} نفر")
    name, clues = random.choice(SPOTS)
    state = {
        "spot": name,
        "clues": clues,
        "shown": 0,
        "guesses": {},
        "phase": "hunt",
    }
    await R.set_status(room_id, "playing", state)
    return state


async def show_clue(room_id: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    shown = int(st.get("shown") or 0)
    clues = st.get("clues") or []
    if shown >= len(clues):
        return {"done": True, "clues": clues}
    clue = clues[shown]
    st["shown"] = shown + 1
    await R.save_state(room_id, st)
    return {"done": False, "clue": clue, "n": st["shown"], "total": len(clues)}


async def guess(room_id: int, uid: int, text: str) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    st.setdefault("guesses", {})[str(uid)] = text.strip()
    await R.save_state(room_id, st)
    return st


async def reveal(room_id: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    spot = st.get("spot") or ""
    winners = [
        int(u) for u, g in (st.get("guesses") or {}).items()
        if spot in (g or "") or (g or "").strip() == spot
    ]
    st["phase"] = "ended"
    st["winners"] = winners
    await R.set_status(room_id, "finished", st)
    return st
