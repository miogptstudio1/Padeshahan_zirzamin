
"""دروغ‌سنج — دو جمله، یکی دروغ."""
from __future__ import annotations
import random
from games.minigames import rooms as R

PAIRS = [
    ("تهران پایتخت ایرانه", "اصفهان پایتخت ایرانه", 1),
    ("آب در صد درجه می‌جوشه", "آب در پنجاه درجه می‌جوشه", 1),
    ("۲+۲ می‌شه ۴", "۲+۲ می‌شه ۵", 1),
    ("خورشید از شرق طلوع می‌کنه", "خورشید از غرب طلوع می‌کنه", 1),
]

async def start(room_id: int) -> dict:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["liar"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['liar']} نفر")
    a, b, lie_idx = random.choice(PAIRS)  # 1 => second is lie if lie_idx=1... store lie as 1 or 2
    # lie_idx in pairs is always 1 meaning second is false in our list
    state = {"s1": a, "s2": b, "lie": 2, "votes": {}, "phase": "vote"}
    await R.set_status(room_id, "playing", state)
    return state

async def vote(room_id: int, uid: int, which: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    st.setdefault("votes", {})[str(uid)] = int(which)
    await R.save_state(room_id, st)
    return st

async def reveal(room_id: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    lie = int(st["lie"])
    winners = [int(u) for u, v in (st.get("votes") or {}).items() if int(v) == lie]
    st["phase"] = "ended"
    st["winners"] = winners
    await R.set_status(room_id, "finished", st)
    return st
