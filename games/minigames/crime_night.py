
"""شب جنایت — هر نفر مظنون با راز."""
from __future__ import annotations
import random
from games.minigames import rooms as R

SECRETS = [
    "شب قتل تو انبار بودی",
    "با مقتول دعوا داشتی",
    "اثر انگشتت روی چاقو بود",
    "فقط شاهد بودی",
    "دروغ گفتی درباره ساعت",
    "پول گرفته بودی که ساکت بمونی",
    "واقعاً بی‌گناهی",
    "سلاح را جابه‌جا کردی",
]

async def start(room_id: int) -> dict:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["crime_night"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['crime_night']} نفر")
    ids = [int(p["telegram_id"]) for p in pl]
    killer = random.choice(ids)
    secrets = {}
    pool = SECRETS[:]
    random.shuffle(pool)
    for i, pid in enumerate(ids):
        secrets[str(pid)] = {
            "secret": pool[i % len(pool)],
            "is_killer": pid == killer,
        }
    state = {"killer": killer, "secrets": secrets, "votes": {}, "phase": "discuss"}
    await R.set_status(room_id, "playing", state)
    return state

async def vote(room_id: int, uid: int, target: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    st.setdefault("votes", {})[str(uid)] = int(target)
    st["phase"] = "vote"
    await R.save_state(room_id, st)
    return st

async def reveal(room_id: int) -> dict:
    from collections import Counter
    r = await R.room(room_id)
    st = R.decode(r["state"])
    votes = st.get("votes") or {}
    accused = Counter(int(v) for v in votes.values()).most_common(1)[0][0] if votes else None
    st["phase"] = "ended"
    st["accused"] = accused
    st["caught"] = accused == int(st["killer"])
    await R.set_status(room_id, "finished", st)
    return st
