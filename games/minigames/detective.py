
"""کارآگاه خصوصی — پرونده چندمرحله‌ای."""
from __future__ import annotations
import random
from typing import Any
from games.minigames import rooms as R

CASES = [
    {
        "title": "قتل در قصر",
        "suspects": ["آشپز", "نگهبان", "وزیر", "مهمان"],
        "killer": "وزیر",
        "clues": [
            "زهر توی شراب بوده.",
            "نگهبان شب شیفت بوده ولی خوابش برده.",
            "وزیر ساعت قتل در انبار شراب دیده شده.",
            "آشپز فقط چاقوهای آشپزخانه رو تمیز کرده.",
        ],
    },
    {
        "title": "سرقت تاج",
        "suspects": ["خدمتکار", "جواهرساز", "پیک", "شاهزاده"],
        "killer": "جواهرساز",
        "clues": [
            "قفل گاوصندوق تخصصی باز شده.",
            "خدمتکار کلید اتاق رو گم کرده بود.",
            "جواهرساز قالب تاج رو قبلاً ساخته بود.",
            "پیک فقط نامه‌ها رو آورد.",
        ],
    },
    {
        "title": "بمب بازار سیاه",
        "suspects": ["دلال", "نگهبان", "مشتری", "پلیس مخفی"],
        "killer": "پلیس مخفی",
        "clues": [
            "سیم‌ها نظامی بودن.",
            "دلال اون روز غایب بود.",
            "پلیس مخفی قبلاً تو انبار رفت‌وآمد داشته.",
            "مشتری فقط چانه می‌زده.",
        ],
    },
]


async def start(room_id: int) -> dict:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["detective"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['detective']} نفر")
    case = random.choice(CASES)
    state = {
        "case": case,
        "clue_index": 0,
        "guesses": {},
        "phase": "clues",
        "revealed": [],
    }
    await R.set_status(room_id, "playing", state)
    return state


async def next_clue(room_id: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    case = st["case"]
    idx = int(st.get("clue_index") or 0)
    clues = case["clues"]
    if idx >= len(clues):
        st["phase"] = "guess"
        await R.save_state(room_id, st)
        return {"done": True, "clues": st.get("revealed") or []}
    clue = clues[idx]
    st["revealed"] = list(st.get("revealed") or []) + [clue]
    st["clue_index"] = idx + 1
    if st["clue_index"] >= len(clues):
        st["phase"] = "guess"
    await R.save_state(room_id, st)
    return {"done": False, "clue": clue, "n": st["clue_index"], "total": len(clues)}


async def guess(room_id: int, uid: int, name: str) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    if st.get("phase") not in {"guess", "clues"}:
        raise ValueError("وقت حدس نیست")
    case = st["case"]
    st.setdefault("guesses", {})[str(uid)] = name.strip()
    await R.save_state(room_id, st)
    return st


async def reveal(room_id: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    case = st["case"]
    killer = case["killer"]
    winners = [int(u) for u, g in (st.get("guesses") or {}).items() if g.strip() == killer]
    st["phase"] = "ended"
    st["killer"] = killer
    st["winners"] = winners
    await R.set_status(room_id, "finished", st)
    return st
