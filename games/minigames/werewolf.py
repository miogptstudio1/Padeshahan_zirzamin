
"""گرگینه — شب/روز ساده."""
from __future__ import annotations
import random
from collections import Counter
from games.minigames import rooms as R

async def start(room_id: int) -> dict:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["werewolf"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['werewolf']} نفر")
    ids = [int(p["telegram_id"]) for p in pl]
    random.shuffle(ids)
    n_ww = max(1, len(ids) // 4)
    wolves = set(ids[:n_ww])
    roles = {str(i): ("گرگینه" if i in wolves else "روستایی") for i in ids}
    state = {
        "roles": roles, "wolves": list(wolves),
        "alive": {str(i): True for i in ids},
        "phase": "night", "night_votes": {}, "day_votes": {}, "day": 1,
    }
    await R.set_status(room_id, "playing", state)
    return state

async def night_vote(room_id: int, uid: int, target: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    if st.get("phase") != "night":
        raise ValueError("الان شب نیست")
    if st.get("roles", {}).get(str(uid)) != "گرگینه":
        raise ValueError("فقط گرگینه‌ها شب رأی می‌دن")
    if not st.get("alive", {}).get(str(uid)):
        raise ValueError("مرده‌ای")
    st.setdefault("night_votes", {})[str(uid)] = int(target)
    await R.save_state(room_id, st)
    return st

async def resolve_night(room_id: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    votes = st.get("night_votes") or {}
    victim = None
    if votes:
        victim, _ = Counter(int(v) for v in votes.values()).most_common(1)[0]
        st["alive"][str(victim)] = False
    st["last_victim"] = victim
    st["phase"] = "day"
    st["day_votes"] = {}
    st["night_votes"] = {}
    await R.save_state(room_id, st)
    return st

async def day_vote(room_id: int, uid: int, target: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    if st.get("phase") != "day":
        raise ValueError("الان روز نیست")
    if not st.get("alive", {}).get(str(uid)):
        raise ValueError("مرده‌ای")
    st.setdefault("day_votes", {})[str(uid)] = int(target)
    await R.save_state(room_id, st)
    return st

async def resolve_day(room_id: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    votes = st.get("day_votes") or {}
    hanged = None
    if votes:
        hanged, _ = Counter(int(v) for v in votes.values()).most_common(1)[0]
        st["alive"][str(hanged)] = False
    st["last_hanged"] = hanged
    alive = [int(u) for u, a in st["alive"].items() if a]
    wolves_alive = [w for w in st.get("wolves", []) if st["alive"].get(str(w))]
    villagers = [u for u in alive if u not in st.get("wolves", [])]
    if not wolves_alive:
        st["phase"] = "ended"; st["winner"] = "villagers"
        await R.set_status(room_id, "finished", st)
    elif len(wolves_alive) >= len(villagers):
        st["phase"] = "ended"; st["winner"] = "wolves"
        await R.set_status(room_id, "finished", st)
    else:
        st["phase"] = "night"
        st["day"] = int(st.get("day") or 1) + 1
        st["day_votes"] = {}
        await R.save_state(room_id, st)
    return st
