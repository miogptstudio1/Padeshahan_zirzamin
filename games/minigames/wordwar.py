
"""نبرد کلمات — آخرین حرف."""
from __future__ import annotations
import random
from typing import Any
from games.minigames import rooms as R

STARTERS = ["پادشاه", "زیرزمین", "خنجر", "قلمرو", "سکه", "سایه", "امپراتوری", "بمب"]


async def start(room_id: int) -> dict:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["wordwar"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['wordwar']} نفر")
    ids = [int(p["telegram_id"]) for p in pl]
    random.shuffle(ids)
    word = random.choice(STARTERS)
    state = {
        "order": ids,
        "turn": 0,
        "last_word": word,
        "used": [word],
        "alive": {str(i): True for i in ids},
        "phase": "play",
    }
    await R.set_status(room_id, "playing", state)
    return state


def current_player(st) -> int | None:
    order = st.get("order") or []
    alive = st.get("alive") or {}
    if not order:
        return None
    for _ in range(len(order)):
        idx = int(st.get("turn") or 0) % len(order)
        pid = int(order[idx])
        if alive.get(str(pid)):
            return pid
        st["turn"] = idx + 1
    return None


async def play_word(room_id: int, uid: int, word: str) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    if st.get("phase") != "play":
        raise ValueError("بازی تموم شده")
    cur = current_player(st)
    if cur is None or int(uid) != int(cur):
        raise ValueError("نوبت تو نیست")
    word = (word or "").strip()
    if len(word) < 2:
        raise ValueError("کلمه کوتاهه")
    last = (st.get("last_word") or "")
    # last letter of previous must match first of new (Persian)
    if last and word[0] != last[-1]:
        raise ValueError(f"باید با «{last[-1]}» شروع بشه")
    used = [w.lower() for w in (st.get("used") or [])]
    if word.lower() in used:
        raise ValueError("این کلمه قبلاً اومده")
    st["used"] = list(st.get("used") or []) + [word]
    st["last_word"] = word
    st["turn"] = int(st.get("turn") or 0) + 1
    await R.save_state(room_id, st)
    return {"ok": True, "next": current_player(st), "last": word}


async def skip_fail(room_id: int, uid: int) -> dict:
    """حذف بازیکن فعلی (نتونست بگه)."""
    r = await R.room(room_id)
    st = R.decode(r["state"])
    cur = current_player(st)
    if cur is None:
        raise ValueError("کسی نمونده")
    if int(uid) not in (int(cur),):  # anyone can trigger fail on current? only self or group - allow any for simplicity
        pass
    st["alive"][str(cur)] = False
    alive = [int(u) for u, a in st["alive"].items() if a]
    if len(alive) <= 1:
        st["phase"] = "ended"
        st["winner_id"] = alive[0] if alive else None
        await R.set_status(room_id, "finished", st)
    else:
        st["turn"] = int(st.get("turn") or 0) + 1
        await R.save_state(room_id, st)
    return st
