
"""جزیره گمشده — منابع محدود و زنده‌ماندن."""
from __future__ import annotations
import random
from typing import Any
from games.minigames import rooms as R

EVENTS = [
    ("🌊 طوفان", -2, "غذا خراب شد"),
    ("🌴 میوه جنگلی", +3, "غذا پیدا شد"),
    ("🐍 مار", -1, "زخمی شدین"),
    ("🪵 چوب خشک", +1, "منابع ساخت"),
    ("🌧️ باران", +2, "آب جمع شد"),
    ("🏚️ خرابه", +2, "جعبه‌ی آذوقه"),
    ("🔥 آتش‌سوزی", -3, "انبار سوخت"),
]


async def start(room_id: int) -> dict:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["island"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['island']} نفر")
    food = 5 + len(pl)
    state = {
        "food": food,
        "day": 1,
        "max_days": 5,
        "alive": {str(int(p["telegram_id"])): True for p in pl},
        "scores": {str(int(p["telegram_id"])): 0 for p in pl},
        "phase": "act",  # act -> resolve
        "actions": {},  # forage|rest|steal
        "log": [],
    }
    await R.set_status(room_id, "playing", state)
    return state


async def act(room_id: int, uid: int, choice: str) -> dict:
    r = await R.room(room_id)
    if not r or r["status"] != "playing":
        raise ValueError("بازی فعال نیست")
    st = R.decode(r["state"])
    if st.get("phase") != "act":
        raise ValueError("الان وقت عمل نیست")
    if not st.get("alive", {}).get(str(uid)):
        raise ValueError("حذف شدی")
    choice = choice.lower()
    if choice not in {"forage", "rest", "steal", "جمع", "استراحت", "دزدی"}:
        raise ValueError("یکی از: جمع · استراحت · دزدی")
    mapping = {"جمع": "forage", "استراحت": "rest", "دزدی": "steal"}
    choice = mapping.get(choice, choice)
    st.setdefault("actions", {})[str(uid)] = choice
    await R.save_state(room_id, st)
    return st


async def resolve_day(room_id: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    actions = st.get("actions") or {}
    food = int(st.get("food") or 0)
    # forage adds, steal risks
    forages = sum(1 for a in actions.values() if a == "forage")
    steals = [uid for uid, a in actions.items() if a == "steal"]
    rests = [uid for uid, a in actions.items() if a == "rest"]
    food += forages * random.randint(1, 2)
    food -= max(0, len([u for u, al in (st.get("alive") or {}).items() if al]) - forages // 2)
    if steals:
        # stealer gains score if not caught
        for s in steals:
            if random.random() < 0.45:
                st["scores"][s] = int(st["scores"].get(s, 0)) - 2
                st.setdefault("log", []).append(f"دزد {s} لو رفت")
            else:
                st["scores"][s] = int(st["scores"].get(s, 0)) + 2
                food = max(0, food - 1)
    for u in rests:
        st["scores"][u] = int(st["scores"].get(u, 0)) + 1
    for u in actions:
        if actions[u] == "forage":
            st["scores"][u] = int(st["scores"].get(u, 0)) + 1
    ev = random.choice(EVENTS)
    food += ev[1]
    st["food"] = max(0, food)
    st.setdefault("log", []).append(f"{ev[0]}: {ev[2]} ({ev[1]:+d} غذا)")
    # starvation
    if st["food"] <= 0:
        alive = [u for u, a in (st.get("alive") or {}).items() if a]
        if alive:
            victim = random.choice(alive)
            st["alive"][victim] = False
            st["log"].append(f"💀 {victim} از گرسنگی افتاد")
    st["actions"] = {}
    day = int(st.get("day") or 1)
    alive_left = [u for u, a in st.get("alive", {}).items() if a]
    if day >= int(st.get("max_days") or 5) or len(alive_left) <= 1:
        st["phase"] = "ended"
        if alive_left:
            best = max(alive_left, key=lambda u: int(st["scores"].get(u, 0)))
            st["winner_id"] = int(best)
        await R.set_status(room_id, "finished", st)
    else:
        st["day"] = day + 1
        st["phase"] = "act"
        await R.save_state(room_id, st)
    return st
