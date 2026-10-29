"""Pure validation rules for empire alliances."""
from __future__ import annotations
import re


def clean_name(value: str) -> str:
    value = " ".join(value.split()).strip()
    if not 3 <= len(value) <= 32:
        raise ValueError("نام اتحاد باید بین ۳ تا ۳۲ نویسه باشد.")
    if any(ord(c) < 32 for c in value):
        raise ValueError("نام اتحاد معتبر نیست.")
    return value


def clean_tag(value: str) -> str:
    value = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,5}", value):
        raise ValueError("برچسب اتحاد باید ۲ تا ۵ حرف انگلیسی یا عدد باشد.")
    return value
