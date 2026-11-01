"""قوانین ارتش پیشرفته و فرماندهان — نسخه ۰.۳۳."""
from __future__ import annotations

# واحدهای تخصصی
UNITS = {
    "infantry": {
        "name": "پیاده‌نظام",
        "cost": 25,
        "power": 4,
        "desc": "نیروی پایهٔ ارتش",
    },
    "archer": {
        "name": "کماندار",
        "cost": 40,
        "power": 6,
        "desc": "قدرت حمله از فاصله",
    },
    "cavalry": {
        "name": "سواره‌نظام",
        "cost": 70,
        "power": 10,
        "desc": "ضربهٔ سریع و متحرک",
    },
    "siege": {
        "name": "مهندس محاصره",
        "cost": 120,
        "power": 16,
        "desc": "برای شکستن دفاع قلمرو",
    },
    "shadow": {
        "name": "سایه‌بان",
        "cost": 90,
        "power": 12,
        "desc": "نیروی ویژهٔ زیرزمین",
    },
}

# فرماندهان قابل استخدام (یک‌بار هر کلید)
COMMANDERS = {
    "reza": {
        "name": "رضا تبرزن",
        "cost": 800,
        "bonus_power": 25,
        "desc": "+۲۵ قدرت ارتش",
    },
    "neda": {
        "name": "ندا کمان‌کش",
        "cost": 1200,
        "bonus_power": 40,
        "desc": "+۴۰ قدرت ارتش",
    },
    "kaveh": {
        "name": "کاوه سپر‌دار",
        "cost": 1500,
        "bonus_power": 35,
        "desc": "+۳۵ قدرت · مناسب دفاع",
    },
    "shahin": {
        "name": "شاهین سایه",
        "cost": 2500,
        "bonus_power": 60,
        "desc": "+۶۰ قدرت · افسانه‌ای",
    },
}

UNIT_ALIASES = {
    "پیاده": "infantry",
    "پیاده‌نظام": "infantry",
    "infantry": "infantry",
    "کماندار": "archer",
    "کمان": "archer",
    "archer": "archer",
    "سواره": "cavalry",
    "سواره‌نظام": "cavalry",
    "cavalry": "cavalry",
    "مهندس": "siege",
    "محاصره": "siege",
    "siege": "siege",
    "سایه": "shadow",
    "سایه‌بان": "shadow",
    "shadow": "shadow",
}

COMMANDER_ALIASES = {
    "رضا": "reza",
    "رضا تبرزن": "reza",
    "reza": "reza",
    "ندا": "neda",
    "ندا کمان‌کش": "neda",
    "neda": "neda",
    "کاوه": "kaveh",
    "کاوه سپر‌دار": "kaveh",
    "kaveh": "kaveh",
    "شاهین": "shahin",
    "شاهین سایه": "shahin",
    "shahin": "shahin",
}


def unit_power(unit_key: str, qty: int) -> int:
    meta = UNITS.get(unit_key)
    if not meta or qty <= 0:
        return 0
    return int(meta["power"]) * int(qty)
