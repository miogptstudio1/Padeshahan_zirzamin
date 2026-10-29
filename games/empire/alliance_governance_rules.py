"""Pure validation rules for alliance proposals."""
def validate_proposal(title: str, description: str, duration_hours: int) -> tuple[str, str, int]:
    title = " ".join((title or "").split()).strip()
    description = " ".join((description or "").split()).strip()
    if not 5 <= len(title) <= 100:
        raise ValueError("عنوان پیشنهاد باید بین ۵ تا ۱۰۰ نویسه باشد.")
    if not 10 <= len(description) <= 1000:
        raise ValueError("توضیح پیشنهاد باید بین ۱۰ تا ۱۰۰۰ نویسه باشد.")
    if not isinstance(duration_hours, int) or isinstance(duration_hours, bool) or not 1 <= duration_hours <= 72:
        raise ValueError("مدت رأی‌گیری باید بین ۱ تا ۷۲ ساعت باشد.")
    return title, description, duration_hours
