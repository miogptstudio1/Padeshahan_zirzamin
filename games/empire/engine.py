"""Pure rules for the Empire economy and territory system."""
from __future__ import annotations

DAILY_REWARD = 100
WORK_REWARD = 25
WORK_COOLDOWN_SECONDS = 60 * 60
DAILY_COOLDOWN_SECONDS = 24 * 60 * 60
MAX_ASSET_LEVEL = 5
ASSETS = {
    "workshop": {"name": "کارگاه", "base_cost": 100, "base_income": 15},
    "club": {"name": "باشگاه", "base_cost": 250, "base_income": 35},
    "factory": {"name": "کارخانه", "base_cost": 500, "base_income": 80},
}
COLLECT_COOLDOWN_SECONDS = 60 * 60
TAX_COOLDOWN_SECONDS = 6 * 60 * 60
MAX_DEFENSE_LEVEL = 5
CITIES = {
    "market": {"name": "بازار مرکزی", "price": 500, "tax": 30, "description": "قلب تجارت شهر"},
    "port": {"name": "بندر قدیمی", "price": 1000, "tax": 60, "description": "مسیر بازرگانی و واردات"},
    "citadel": {"name": "ارگ سلطنتی", "price": 2000, "tax": 120, "description": "مرکز نفوذ سیاسی"},
    "industrial": {"name": "منطقه صنعتی", "price": 4000, "tax": 250, "description": "کارگاه‌ها و کارخانه‌ها"},
    "capital": {"name": "پایتخت زیرزمین", "price": 8000, "tax": 500, "description": "گران‌ترین و پردرآمدترین قلمرو"},
    "slums": {"name": "محلهٔ زاغه‌ها", "price": 350, "tax": 20, "description": "کوچه‌های تاریک و قاچاق"},
    "mines": {"name": "معادن زغال", "price": 800, "tax": 45, "description": "منابع خام زیرزمین"},
    "casino": {"name": "کازینو سیاه", "price": 1500, "tax": 90, "description": "قمار و پولشویی"},
    "temple": {"name": "معبد سایه‌ها", "price": 2500, "tax": 140, "description": "مرکز آیین‌های مخفی"},
    "arsenal": {"name": "انبار تسلیحات", "price": 3200, "tax": 180, "description": "سلاح و مهمات"},
    "harbor": {"name": "اسکله مه", "price": 1800, "tax": 100, "description": "قاچاق دریایی"},
    "bazaar": {"name": "بازار شب", "price": 600, "tax": 35, "description": "معاملات غیررسمی"},
    "fort": {"name": "دژ مرزی", "price": 5000, "tax": 280, "description": "خط مقدم جنگ‌ها"},
    "lab": {"name": "آزمایشگاه متروکه", "price": 2200, "tax": 130, "description": "تکنولوژی غیرقانونی"},
    "palace": {"name": "کاخ زیرزمینی", "price": 10000, "tax": 600, "description": "نماد قدرت مطلق"},
    # مناطق جدید نقشه (۰.۳۵)
    "ruins_gate": {"name": "دروازه ویرانه‌ها", "price": 900, "tax": 50, "description": "شمال · ورودی سرزمین مرده"},
    "bone_bridge": {"name": "پل استخوان", "price": 1100, "tax": 65, "description": "شمال · گذرگاه خطرناک"},
    "frost_camp": {"name": "اردوگاه یخ", "price": 1600, "tax": 95, "description": "شمال · سرمای دائمی"},
    "ash_market": {"name": "بازار خاکستر", "price": 700, "tax": 40, "description": "شرق · تجارت سیاه"},
    "red_docks": {"name": "اسکله سرخ", "price": 1400, "tax": 85, "description": "شرق · قاچاق دریایی"},
    "silk_den": {"name": "لانه ابریشم", "price": 2100, "tax": 125, "description": "شرق · ثروت پنهان"},
    "cinder_pit": {"name": "گودال اخگر", "price": 1300, "tax": 75, "description": "جنوب · معدن داغ"},
    "sand_keep": {"name": "دژ شن", "price": 2800, "tax": 160, "description": "جنوب · دفاع سخت"},
    "mirage_well": {"name": "چاه سراب", "price": 950, "tax": 55, "description": "جنوب · آب و باج"},
    "fog_alley": {"name": "کوچه مه", "price": 550, "tax": 32, "description": "غرب · کمین و دزدی"},
    "iron_yard": {"name": "حیاط آهن", "price": 1900, "tax": 110, "description": "غرب · ساخت سلاح"},
    "night_spire": {"name": "برج شب", "price": 4500, "tax": 260, "description": "غرب · دیده‌بانی بلند"},
    "under_forum": {"name": "میدان زیر", "price": 1200, "tax": 70, "description": "مرکز · تجمع و سیاست"},
    "black_vault": {"name": "خزانه سیاه", "price": 6000, "tax": 320, "description": "مرکز · ثروت سنگین"},
    "echo_tunnels": {"name": "تونل پژواک", "price": 1700, "tax": 100, "description": "زیر · مسیر مخفی"},
}
STARTER_OUTPOSTS = {
    f"outpost_{i}": {
        "name": f"پناهگاه مرزی {i}",
        "price": 0,
        "tax": 12,
        "description": "قلمرو اولیه بازیکن — پایگاه حمله",
    }
    for i in range(1, 61)
}
CITIES.update(STARTER_OUTPOSTS)



def asset_cost(asset_key: str, current_level: int) -> int:
    if asset_key not in ASSETS:
        raise ValueError("دارایی نامعتبر است.")
    if current_level < 0 or current_level >= MAX_ASSET_LEVEL:
        raise ValueError("این دارایی به حداکثر سطح رسیده است.")
    return ASSETS[asset_key]["base_cost"] * (current_level + 1)


def hourly_income(asset_key: str, level: int) -> int:
    if asset_key not in ASSETS or level < 1 or level > MAX_ASSET_LEVEL:
        raise ValueError("سطح یا نوع دارایی نامعتبر است.")
    return ASSETS[asset_key]["base_income"] * level


def can_collect(last_collected_epoch: float | None, now_epoch: float) -> bool:
    return last_collected_epoch is None or now_epoch - last_collected_epoch >= COLLECT_COOLDOWN_SECONDS


def defense_upgrade_cost(city_key: str, current_level: int) -> int:
    if city_key not in CITIES:
        raise ValueError("قلمرو نامعتبر است.")
    if current_level < 0 or current_level >= MAX_DEFENSE_LEVEL:
        raise ValueError("دفاع این قلمرو به حداکثر سطح رسیده است.")
    return CITIES[city_key]["price"] * (current_level + 1) // 2


def city_tax(city_key: str, defense_level: int = 0) -> int:
    if city_key not in CITIES or defense_level < 0 or defense_level > MAX_DEFENSE_LEVEL:
        raise ValueError("قلمرو یا سطح دفاع نامعتبر است.")
    return CITIES[city_key]["tax"]


# Territory warfare (v0.15)
WAR_PREPARATION_SECONDS = 10 * 60
WAR_FEE_RATE = 0.10
WAR_ATTACK_BASE = 50
WAR_DEFENSE_BASE = 50
WAR_ATTACK_CITY_DEFENSE_BONUS = 20
WAR_DEFENSE_LEVEL_BONUS = 25
WAR_CITY_COUNT_BONUS = 15
WAR_RANDOM_MAX = 30

def war_fee(target_city_price: int) -> int:
    if target_city_price <= 0:
        raise ValueError("قیمت قلمرو نامعتبر است.")
    return max(1, int(target_city_price * WAR_FEE_RATE))

def attack_power(owned_city_count: int, attack_city_defense: int, roll: int) -> int:
    if owned_city_count < 1 or attack_city_defense < 0 or roll < 0 or roll > WAR_RANDOM_MAX:
        raise ValueError("پارامتر قدرت حمله نامعتبر است.")
    return WAR_ATTACK_BASE + owned_city_count * WAR_CITY_COUNT_BONUS + attack_city_defense * WAR_ATTACK_CITY_DEFENSE_BONUS + roll

def defense_power(owned_city_count: int, target_defense: int) -> int:
    if owned_city_count < 1 or target_defense < 0 or target_defense > MAX_DEFENSE_LEVEL:
        raise ValueError("پارامتر قدرت دفاع نامعتبر است.")
    return WAR_DEFENSE_BASE + owned_city_count * WAR_CITY_COUNT_BONUS + target_defense * WAR_DEFENSE_LEVEL_BONUS

def war_attacker_wins(attack: int, defense: int) -> bool:
    if attack < 0 or defense < 0:
        raise ValueError("قدرت نبرد نمی‌تواند منفی باشد.")
    return attack > defense


def war_result_message(result: dict) -> str:
    """Create a consistent Persian notification for a resolved war."""
    if result.get("cancelled"):
        return f"⚠️ جنگ #{result['id']} لغو شد؛ مالکیت قلمرو هدف پیش از تعیین نتیجه تغییر کرده بود."
    if result.get("won"):
        return (f"🏆 نتیجهٔ خودکار جنگ #{result['id']}: پیروزی مهاجم!\n"
                f"قلمرو «{result['target_name']}» تصرف شد.\n"
                f"قدرت حمله: {result['attack_power']} | قدرت دفاع: {result['defense_power']}")
    return (f"🛡️ نتیجهٔ خودکار جنگ #{result['id']}: مدافع پیروز شد و قلمرو «{result['target_name']}» را حفظ کرد.\n"
            f"قدرت حمله: {result['attack_power']} | قدرت دفاع: {result['defense_power']}")


# Army system (v0.17)
SOLDIER_RECRUIT_COST = 20
MAX_SOLDIERS = 500
SOLDIER_POWER = 3

def recruit_cost(count: int) -> int:
    if not isinstance(count, int) or count < 1 or count > 100:
        raise ValueError("هر بار باید بین ۱ تا ۱۰۰ سرباز استخدام کنی.")
    return count * SOLDIER_RECRUIT_COST

def army_power_bonus(soldiers: int) -> int:
    if not isinstance(soldiers, int) or soldiers < 0 or soldiers > MAX_SOLDIERS:
        raise ValueError("تعداد سرباز نامعتبر است.")
    return soldiers * SOLDIER_POWER
