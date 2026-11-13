
"""حدس کلمه — مثل هنگمن ساده."""
from __future__ import annotations
import random
from games.minigames import rooms as R

WORDS = ["امپراتوری", "زیرزمین", "خائن", "پناهگاه", "جاسوس", "مالیات", "کودتا", "بازار"]

async def start(room_id: int) -> dict:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["wordguess"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['wordguess']} نفر")
    word = random.choice(WORDS)
    state = {
        "word": word,
        "revealed": ["_" if c != " " else " " for c in word],
        "wrong": 0,
        "max_wrong": 7,
        "guessed": [],
        "phase": "play",
    }
    await R.set_status(room_id, "playing", state)
    return state

async def guess_letter(room_id: int, uid: int, letter: str) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    if st.get("phase") != "play":
        raise ValueError("تموم شده")
    letter = (letter or "").strip()[:1]
    if not letter:
        raise ValueError("یک حرف بفرست")
    if letter in st.get("guessed", []):
        raise ValueError("قبلاً زدی")
    st.setdefault("guessed", []).append(letter)
    word = st["word"]
    if letter in word:
        st["revealed"] = [c if c == letter or st["revealed"][i] != "_" else st["revealed"][i]
                          for i, c in enumerate(word)]
        # fix properly
        rev = list(st["revealed"])
        for i, c in enumerate(word):
            if c == letter:
                rev[i] = c
        st["revealed"] = rev
        if "_" not in st["revealed"]:
            st["phase"] = "ended"
            st["winner_id"] = int(uid)
            await R.set_status(room_id, "finished", st)
            return {"ok": True, "done": True, "state": st}
    else:
        st["wrong"] = int(st.get("wrong") or 0) + 1
        if st["wrong"] >= int(st.get("max_wrong") or 7):
            st["phase"] = "ended"
            await R.set_status(room_id, "finished", st)
            return {"ok": False, "done": True, "state": st}
    await R.save_state(room_id, st)
    return {"ok": letter in word, "done": False, "state": st}
