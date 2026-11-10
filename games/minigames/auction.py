
"""مزایده مرگبار — بودجه محدود."""
from __future__ import annotations
import random
from typing import Any
from games.minigames import rooms as R

ITEMS = [
    ("🗡️ خنجر زهرآلود", 40),
    ("📜 نقشه گنج", 35),
    ("💎 نگین سیاه", 50),
    ("🛡️ سپر ترک‌خورده", 25),
    ("🧪 معجون شانس", 30),
]


async def start(room_id: int) -> dict:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["auction"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['auction']} نفر")
    budget = {str(int(p["telegram_id"])): 100 for p in pl}
    items = random.sample(ITEMS, k=min(4, len(ITEMS)))
    state = {
        "budget": budget,
        "items": [{"name": n, "min": m} for n, m in items],
        "index": 0,
        "bids": {},
        "won": {},
        "phase": "bid",
    }
    await R.set_status(room_id, "playing", state)
    return state


def current_item(st):
    idx = int(st.get("index") or 0)
    items = st.get("items") or []
    return items[idx] if idx < len(items) else None


async def bid(room_id: int, uid: int, amount: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    if st.get("phase") != "bid":
        raise ValueError("مزایده فعال نیست")
    item = current_item(st)
    if not item:
        raise ValueError("آیتمی نمانده")
    amount = int(amount)
    bud = int((st.get("budget") or {}).get(str(uid), 0))
    if amount < int(item["min"]):
        raise ValueError(f"حداقل {item['min']}")
    if amount > bud:
        raise ValueError(f"بودجه {bud}")
    st.setdefault("bids", {})[str(uid)] = amount
    await R.save_state(room_id, st)
    return st


async def close_item(room_id: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    item = current_item(st)
    if not item:
        raise ValueError("تموم شده")
    bids = st.get("bids") or {}
    if not bids:
        st["index"] = int(st["index"]) + 1
        st["bids"] = {}
        if st["index"] >= len(st["items"]):
            st["phase"] = "ended"
            await R.set_status(room_id, "finished", st)
        else:
            await R.save_state(room_id, st)
        return {"passed": True, "state": st}
    winner, price = max(bids.items(), key=lambda x: int(x[1]))
    st["budget"][winner] = int(st["budget"].get(winner, 0)) - int(price)
    st.setdefault("won", {}).setdefault(winner, []).append(item["name"])
    st["index"] = int(st["index"]) + 1
    st["bids"] = {}
    st["last"] = {"winner": int(winner), "item": item["name"], "price": int(price)}
    if st["index"] >= len(st["items"]):
        st["phase"] = "ended"
        # most items wins
        best = max(st["won"].items(), key=lambda x: len(x[1]))[0] if st.get("won") else None
        st["winner_id"] = int(best) if best else None
        await R.set_status(room_id, "finished", st)
    else:
        await R.save_state(room_id, st)
    return {"passed": False, "state": st}
