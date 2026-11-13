
"""کد مخفی — حدس عدد ۴ رقمی."""
from __future__ import annotations
import random
from games.minigames import rooms as R

async def start(room_id: int) -> dict:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["seccode"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['seccode']} نفر")
    code = "".join(str(random.randint(0, 9)) for _ in range(4))
    state = {"code": code, "tries": 0, "max_tries": 12, "phase": "play"}
    await R.set_status(room_id, "playing", state)
    return state

async def guess(room_id: int, uid: int, text: str) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    guess = "".join(ch for ch in (text or "") if ch.isdigit())[:4]
    if len(guess) != 4:
        raise ValueError("۴ رقم بده")
    st["tries"] = int(st.get("tries") or 0) + 1
    code = st["code"]
    bulls = sum(1 for i in range(4) if guess[i] == code[i])
    cows = sum(1 for c in guess if c in code) - bulls
    if guess == code:
        st["phase"] = "ended"
        st["winner_id"] = int(uid)
        await R.set_status(room_id, "finished", st)
        return {"ok": True, "bulls": bulls, "cows": cows, "state": st}
    if st["tries"] >= int(st.get("max_tries") or 12):
        st["phase"] = "ended"
        await R.set_status(room_id, "finished", st)
        return {"ok": False, "fail": True, "bulls": bulls, "cows": cows, "state": st}
    await R.save_state(room_id, st)
    return {"ok": False, "bulls": bulls, "cows": cows, "tries": st["tries"], "state": st}
