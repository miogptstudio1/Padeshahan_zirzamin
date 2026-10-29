"""Pure helpers for alliance season calculations; no database dependency."""
from datetime import datetime, timezone


def current_season_key(now: datetime | None = None) -> str:
    """Return the current calendar quarter key in UTC."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    return f"{now.year}-Q{((now.month - 1) // 3) + 1}"


def defense_bonus_for_coins(coins: int) -> int:
    if not isinstance(coins, int) or not 10 <= coins <= 1000:
        raise ValueError("کمک دفاعی باید بین ۱۰ تا ۱۰۰۰ سکه باشد.")
    return coins // 10
