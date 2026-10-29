"""Telegram Mini App initData verification (stdlib only)."""
from __future__ import annotations
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class TelegramAuthError(ValueError):
    pass


def validate_init_data(init_data: str, bot_token: str, *, max_age_seconds: int = 86_400, now: int | None = None) -> dict:
    if not init_data or not bot_token:
        raise TelegramAuthError("اطلاعات ورود تلگرام موجود نیست.")
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError as exc:
        raise TelegramAuthError("فرمت اطلاعات ورود نامعتبر است.") from exc
    received_hash = pairs.pop("hash", None)
    if not received_hash or "auth_date" not in pairs or "user" not in pairs:
        raise TelegramAuthError("اطلاعات ورود تلگرام ناقص است.")
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise TelegramAuthError("امضای ورود تلگرام معتبر نیست.")
    try:
        auth_date = int(pairs["auth_date"])
        user = json.loads(pairs["user"])
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TelegramAuthError("اطلاعات کاربر تلگرام نامعتبر است.") from exc
    current = int(time.time()) if now is None else now
    if auth_date > current + 60 or current - auth_date > max_age_seconds:
        raise TelegramAuthError("اطلاعات ورود منقضی شده است؛ وب‌اپ را دوباره باز کن.")
    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        raise TelegramAuthError("شناسهٔ کاربر تلگرام معتبر نیست.")
    return {"user": user, "auth_date": auth_date}
