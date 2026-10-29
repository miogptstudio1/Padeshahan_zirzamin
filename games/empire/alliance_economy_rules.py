"""Pure constants and validation helpers for alliance economy."""
DAILY_REWARD = 50
MIN_TRANSFER = 10
MAX_TRANSFER = 10_000


def validate_transfer_amount(amount: int) -> int:
    if not isinstance(amount, int) or isinstance(amount, bool) or not MIN_TRANSFER <= amount <= MAX_TRANSFER:
        raise ValueError(f"مبلغ باید بین {MIN_TRANSFER} تا {MAX_TRANSFER} سکه باشد.")
    return amount


def war_loot_for_price(city_price: int) -> int:
    """Return 10% of the target territory price, with a 25-coin floor."""
    if not isinstance(city_price, int) or isinstance(city_price, bool) or city_price < 0:
        raise ValueError("قیمت قلمرو نامعتبر است.")
    return max(25, city_price // 10)
