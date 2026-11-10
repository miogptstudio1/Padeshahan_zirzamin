
"""نبرد امپراتوری‌ها — دو تیم، دور حمله."""
from __future__ import annotations
import random
from typing import Any
from games.minigames import rooms as R


async def start(room_id: int) -> dict:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["empirewar"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['empirewar']} نفر")
    ids = [int(p["telegram_id"]) for p in pl]
    random.shuffle(ids)
    mid = len(ids) // 2
    red, blue = ids[:mid], ids[mid:]
    state = {
        "red": red,
        "blue": blue,
        "hp_red": 30 + 5 * len(red),
        "hp_blue": 30 + 5 * len(blue),
        "round": 1,
        "max_rounds": 5,
        "phase": "battle",
        "actions": {},  # uid -> attack|defend
    }
    await R.set_status(room_id, "playing", state)
    return state


def team_of(st, uid: int) -> str | None:
    if int(uid) in [int(x) for x in st.get("red") or []]:
        return "red"
    if int(uid) in [int(x) for x in st.get("blue") or []]:
        return "blue"
    return None


async def act(room_id: int, uid: int, choice: str) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    if st.get("phase") != "battle":
        raise ValueError("نبرد فعال نیست")
    if not team_of(st, uid):
        raise ValueError("تو این نبرد نیستی")
    choice = {"حمله": "attack", "دفاع": "defend"}.get(choice, choice)
    if choice not in {"attack", "defend"}:
        raise ValueError("حمله یا دفاع")
    st.setdefault("actions", {})[str(uid)] = choice
    await R.save_state(room_id, st)
    return st


async def resolve_round(room_id: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    actions = st.get("actions") or {}
    dmg_to_blue = 0
    dmg_to_red = 0
    for uid, act in actions.items():
        team = team_of(st, int(uid))
        if act == "attack":
            dmg = random.randint(2, 5)
            if team == "red":
                dmg_to_blue += dmg
            elif team == "blue":
                dmg_to_red += dmg
        elif act == "defend":
            if team == "red":
                dmg_to_red = max(0, dmg_to_red - 2)
            elif team == "blue":
                dmg_to_blue = max(0, dmg_to_blue - 2)
    # defend reduces incoming - apply after counting attacks better:
    red_def = sum(1 for u, a in actions.items() if a == "defend" and team_of(st, int(u)) == "red")
    blue_def = sum(1 for u, a in actions.items() if a == "defend" and team_of(st, int(u)) == "blue")
    dmg_to_red = 0
    dmg_to_blue = 0
    for uid, act in actions.items():
        team = team_of(st, int(uid))
        if act != "attack":
            continue
        dmg = random.randint(2, 5)
        if team == "red":
            dmg_to_blue += max(1, dmg - blue_def)
        else:
            dmg_to_red += max(1, dmg - red_def)
    st["hp_red"] = max(0, int(st["hp_red"]) - dmg_to_red)
    st["hp_blue"] = max(0, int(st["hp_blue"]) - dmg_to_blue)
    st["last_dmg"] = {"to_red": dmg_to_red, "to_blue": dmg_to_blue}
    st["actions"] = {}
    rnd = int(st.get("round") or 1)
    if st["hp_red"] <= 0 or st["hp_blue"] <= 0 or rnd >= int(st.get("max_rounds") or 5):
        st["phase"] = "ended"
        if st["hp_red"] > st["hp_blue"]:
            st["winner"] = "red"
        elif st["hp_blue"] > st["hp_red"]:
            st["winner"] = "blue"
        else:
            st["winner"] = "draw"
        await R.set_status(room_id, "finished", st)
    else:
        st["round"] = rnd + 1
        await R.save_state(room_id, st)
    return st
