
"""پانتومیم متنی — توضیح بدون گفتن خود کلمه."""
from __future__ import annotations
import random
from games.minigames import rooms as R

WORDS = ["خنجر", "پادشاه", "زندان", "کشتی", "آتش", "گنج", "ماسک", "پل"]

async def start(room_id: int) -> dict:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["pantomime"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['pantomime']} نفر")
    ids = [int(p["telegram_id"]) for p in pl]
    actor = random.choice(ids)
    word = random.choice(WORDS)
    state = {"actor": actor, "word": word, "phase": "play", "winner_id": None}
    await R.set_status(room_id, "playing", state)
    return state

async def guess(room_id: int, uid: int, text: str) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    if int(uid) == int(st.get("actor") or 0):
        raise ValueError("توضیح‌دهنده حدس نمی‌زنه")
    if (text or "").strip() == st.get("word"):
        st["phase"] = "ended"
        st["winner_id"] = int(uid)
        await R.set_status(room_id, "finished", st)
        return {"ok": True, "state": st}
    return {"ok": False, "state": st}
