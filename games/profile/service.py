
"""جنسیت و پروفایل ساده بازیکن."""
from __future__ import annotations
from typing import Any

from core.database import db

GENDERS = {
    "male": {"key": "male", "label": "پسر", "emoji": "👨"},
    "female": {"key": "female", "label": "دختر", "emoji": "👩"},
    "other": {"key": "other", "label": "نامشخص", "emoji": "🧑"},
}


async def get_gender(user_id: int) -> str | None:
    async with db().acquire() as conn:
        try:
            g = await conn.fetchval("SELECT gender FROM users WHERE telegram_id=$1", int(user_id))
        except Exception:
            return None
    if g and g in GENDERS:
        return g
    return None


async def set_gender(user_id: int, gender: str) -> dict[str, Any]:
    gender = (gender or "").strip().lower()
    if gender not in GENDERS:
        raise ValueError("جنسیت نامعتبره. یکی از اینا: پسر · دختر · نامشخص")
    async with db().acquire() as conn:
        await conn.execute(
            "UPDATE users SET gender=$2 WHERE telegram_id=$1",
            int(user_id),
            gender,
        )
    meta = GENDERS[gender]
    return {"gender": gender, "label": meta["label"], "emoji": meta["emoji"]}


async def gender_label(user_id: int) -> str:
    g = await get_gender(user_id)
    if not g:
        return "انتخاب‌نشده"
    m = GENDERS[g]
    return f"{m['emoji']} {m['label']}"


async def needs_gender(user_id: int) -> bool:
    return await get_gender(user_id) is None
