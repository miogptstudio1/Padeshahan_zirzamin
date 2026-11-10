
"""پادشاه خیانت — رأی برای تاج؛ در هر دور ممکنه کسی خیانت کنه."""
from __future__ import annotations
import random
from collections import Counter
from typing import Any

from games.minigames import rooms as R


async def start(room_id: int) -> dict[str, Any]:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["kingbetray"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['kingbetray']} نفر.")
    ids = [int(p["telegram_id"]) for p in pl]
    # یکی خائن مخفی
    traitor = random.choice(ids)
    scores = {str(i): 0 for i in ids}
    state = {
        "traitor_id": traitor,
        "scores": scores,
        "round": 1,
        "max_rounds": 3,
        "phase": "nominate",  # nominate -> vote -> resolve
        "nominations": {},
        "votes": {},
        "king_id": None,
        "history": [],
    }
    await R.set_status(room_id, "playing", state)
    return state


async def nominate(room_id: int, voter_id: int, candidate_id: int) -> dict:
    r = await R.room(room_id)
    if not r or r["status"] != "playing":
        raise ValueError("بازی فعال نیست.")
    st = R.decode(r["state"])
    if st.get("phase") != "nominate":
        raise ValueError("الان وقت معرفی نامزد نیست.")
    st.setdefault("nominations", {})[str(voter_id)] = int(candidate_id)
    await R.save_state(room_id, st)
    return st


async def open_vote(room_id: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    noms = list(st.get("nominations") or {}).values()
    if not noms:
        raise ValueError("هنوز کسی نامزد نشده.")
    st["phase"] = "vote"
    st["votes"] = {}
    st["candidates"] = list({int(x) for x in noms})
    await R.save_state(room_id, st)
    return st


async def vote_king(room_id: int, voter_id: int, candidate_id: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    if st.get("phase") != "vote":
        raise ValueError("الان رأی‌گیری پادشاه نیست.")
    if int(candidate_id) not in set(st.get("candidates") or []):
        raise ValueError("این نفر نامزد نیست.")
    st.setdefault("votes", {})[str(voter_id)] = int(candidate_id)
    await R.save_state(room_id, st)
    return st


async def resolve_round(room_id: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    votes = st.get("votes") or {}
    if not votes:
        raise ValueError("رأیی نیست.")
    c = Counter(int(v) for v in votes.values())
    king, _ = c.most_common(1)[0]
    st["king_id"] = king
    # امتیاز
    scores = st.setdefault("scores", {})
    scores[str(king)] = int(scores.get(str(king), 0)) + 2
    # خائن اگر پادشاه نشد +1 پنهان (برای پایان)
    traitor = int(st["traitor_id"])
    if king != traitor:
        scores[str(traitor)] = int(scores.get(str(traitor), 0)) + 1
    else:
        # خائن تاج گرفت — همه غیرخائن - امتیاز
        for k in list(scores.keys()):
            if int(k) != traitor:
                scores[k] = int(scores.get(k, 0)) - 1
    st["history"] = list(st.get("history") or []) + [{
        "round": st.get("round"),
        "king": king,
        "traitor_won_crown": king == traitor,
    }]
    rnd = int(st.get("round") or 1)
    if rnd >= int(st.get("max_rounds") or 3):
        st["phase"] = "ended"
        # برنده بالاترین امتیاز (در صورت تساوی غیرخائن ترجیح)
        best = sorted(
            ((int(k), int(v)) for k, v in scores.items()),
            key=lambda x: (-x[1], x[0] == traitor),
        )[0][0]
        st["winner_id"] = best
        await R.set_status(room_id, "finished", st)
    else:
        st["round"] = rnd + 1
        st["phase"] = "nominate"
        st["nominations"] = {}
        st["votes"] = {}
        st["candidates"] = []
        await R.save_state(room_id, st)
    return st
