"""Pure validation rules for alliance notifications."""
CATEGORIES = {
    "treasury": "خزانه و امور مالی",
    "rank": "تغییر رتبه و مدیریت اعضا",
    "war": "جنگ‌ها و غنیمت‌ها",
    "buildings": "ساختمان‌ها و سپر دفاعی",
    "general": "رویدادهای عمومی اتحاد",
}

def validate_preferences(telegram_enabled, categories):
    if not isinstance(telegram_enabled, bool):
        raise ValueError("وضعیت اعلان تلگرام باید روشن یا خاموش باشد.")
    if not isinstance(categories, dict):
        raise ValueError("تنظیمات دسته‌بندی اعلان نامعتبر است.")
    unknown = set(categories) - set(CATEGORIES)
    if unknown:
        raise ValueError("دسته‌بندی اعلان نامعتبر است.")
    if any(not isinstance(value, bool) for value in categories.values()):
        raise ValueError("هر دسته‌بندی باید روشن یا خاموش باشد.")
    return {"telegram_enabled": telegram_enabled, "categories": dict(categories)}
