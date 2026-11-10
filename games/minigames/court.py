
"""دادگاه سلطنتی — متهم و رأی."""
from __future__ import annotations
import random
from collections import Counter
from typing import Any
from games.minigames import rooms as R

CHARGES = [
    "خیانت به تاج",
    "دزدی از خزانه",
    "سحر ممنوع",
    "قتل در قصر",
    "جاسوسی برای دشمن",
]


async def start(room_id: int) -> dict:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["court"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['court']} نفر")
    ids = [int(p["telegram_id"]) for p in pl]
    accused = random.choice(ids)
    state = {
        "accused_id": accused,
        "charge": random.choice(CHARGES),
        "guilty": random.choice([True, False]),
        "phase": "debate",
        "votes": {},  # guilty|innocent
    }
    await R.set_status(room_id, "playing", state)
    return state


async def vote(room_id: int, uid: int, choice: str) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    if int(uid) == int(st.get("accused_id") or 0):
        raise ValueError("متهم رأی نمی‌ده")
    choice = {"گناهکار": "guilty", "بیگناه": "innocent"}.get(choice, choice)
    if choice not in {"guilty", "innocent"}:
        raise ValueError("گناهکار یا بیگناه")
    st.setdefault("votes", {})[str(uid)] = choice
    st["phase"] = "vote"
    await R.save_state(room_id, st)
    return st


async def verdict(room_id: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    votes = list((st.get("votes") or {}).values())
    if not votes:
        raise ValueError("رأیی نیست")
    c = Counter(votes)
    decision = c.most_common(1)[0][0]
    correct = (decision == "guilty") == bool(st.get("guilty"))
    st["phase"] = "ended"
    st["decision"] = decision
    st["correct"] = correct
    await R.set_status(room_id, "finished", st)
    return st
