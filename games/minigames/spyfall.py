
"""جاسوس ناشناس — یکی مکان رو نمی‌دونه."""
from __future__ import annotations
import random
from typing import Any

from games.minigames import rooms as R

LOCATIONS = [
    ("بانک", ["مدیر", "نگهبان", "مشتری", "سارق", "تحویلداری"]),
    ("بیمارستان", ["پزشک", "پرستار", "بیمار", "جراح", "امنیت"]),
    ("مدرسه", ["معلم", "دانش‌آموز", "ناظم", "آشپز", "سرایدار"]),
    ("زیرزمین قاچاق", ["رئیس", "حامل", "نگهبان", "مشتری", "حسابدار"]),
    ("کاخ سلطنتی", ["شاه", "وزیر", "نگهبان", "آشپز", "جاسوس دربار"]),
    ("ایستگاه فضایی", ["فرمانده", "مهندس", "پزشک", "خلبان", "دانشمند"]),
    ("رستوران لوکس", ["سرآشپز", "گارسون", "مشتری", "منتقد", "مدیر"]),
    ("زندان", ["زندانبان", "زندانی", "وکیل", "پزشک", "بازپرس"]),
    ("بازار سیاه", ["فروشنده", "خریدار", "نگهبان", "پلیس مخفی", "دلال"]),
    ("کشتی دزدان دریایی", ["کاپیتان", "ملوان", "آشپز", "زندانی", "نقشه‌خوان"]),
]


async def start(room_id: int) -> dict[str, Any]:
    pl = await R.players(room_id)
    if len(pl) < R.MIN_PLAYERS["spyfall"]:
        raise ValueError(f"حداقل {R.MIN_PLAYERS['spyfall']} نفر لازم است.")
    loc_name, roles = random.choice(LOCATIONS)
    ids = [int(p["telegram_id"]) for p in pl]
    spy_id = random.choice(ids)
    assignments = {}
    role_pool = roles[:]
    random.shuffle(role_pool)
    for i, pid in enumerate(ids):
        if pid == spy_id:
            assignments[str(pid)] = {"is_spy": True, "role": "جاسوس", "location": None}
        else:
            assignments[str(pid)] = {
                "is_spy": False,
                "role": role_pool[i % len(role_pool)],
                "location": loc_name,
            }
    state = {
        "location": loc_name,
        "spy_id": spy_id,
        "assignments": assignments,
        "votes": {},
        "phase": "discuss",
        "round": 1,
    }
    await R.set_status(room_id, "playing", state)
    return state


async def cast_vote(room_id: int, voter_id: int, target_id: int) -> dict:
    r = await R.room(room_id)
    if not r or r["status"] != "playing":
        raise ValueError("بازی فعال نیست.")
    st = R.decode(r["state"])
    if st.get("phase") != "vote":
        raise ValueError("الان وقت رأی نیست. اول «رأی جاسوس» بزنین.")
    st.setdefault("votes", {})[str(voter_id)] = int(target_id)
    await R.save_state(room_id, st)
    return st


async def start_vote(room_id: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    st["phase"] = "vote"
    st["votes"] = {}
    await R.save_state(room_id, st)
    return st


async def resolve_vote(room_id: int) -> dict:
    r = await R.room(room_id)
    st = R.decode(r["state"])
    votes = st.get("votes") or {}
    if not votes:
        raise ValueError("رأیی ثبت نشده.")
    from collections import Counter
    c = Counter(int(v) for v in votes.values())
    accused, n = c.most_common(1)[0]
    spy = int(st["spy_id"])
    spy_caught = accused == spy
    st["phase"] = "ended"
    st["result"] = {
        "accused": accused,
        "spy_id": spy,
        "spy_caught": spy_caught,
        "location": st["location"],
    }
    await R.set_status(room_id, "finished", st)
    return st["result"]
