"""Pure rules for the in-game equipment shop and reward boxes."""
from __future__ import annotations
import random

ITEMS = {
    "wood_sword": {"name": "شمشیر چوبی", "kind": "weapon", "price": 150, "attack": 5, "defense": 0, "rarity": "معمولی"},
    "iron_sword": {"name": "شمشیر آهنی", "kind": "weapon", "price": 500, "attack": 12, "defense": 0, "rarity": "کمیاب"},
    "shadow_blade": {"name": "تیغهٔ سایه", "kind": "weapon", "price": 1200, "attack": 25, "defense": 0, "rarity": "حماسی"},
    "royal_blade": {"name": "شمشیر سلطنتی", "kind": "weapon", "price": 3000, "attack": 45, "defense": 0, "rarity": "افسانه‌ای"},
    # Firearms are fictional/in-game equipment; stats are game balance values only.
    "service_pistol": {"name": "تپانچهٔ نگهبان", "kind": "weapon", "category": "firearm", "price": 450, "attack": 11, "defense": 0, "rarity": "معمولی"},
    "heavy_pistol": {"name": "تپانچهٔ سنگین", "kind": "weapon", "category": "firearm", "price": 850, "attack": 17, "defense": 0, "rarity": "کمیاب"},
    "compact_smg": {"name": "مسلسل دستی فشرده", "kind": "weapon", "category": "firearm", "price": 1100, "attack": 20, "defense": 0, "rarity": "کمیاب"},
    "storm_smg": {"name": "مسلسل طوفان", "kind": "weapon", "category": "firearm", "price": 1650, "attack": 27, "defense": 0, "rarity": "حماسی"},
    "guard_rifle": {"name": "تفنگ نگهبان", "kind": "weapon", "category": "firearm", "price": 900, "attack": 18, "defense": 0, "rarity": "کمیاب"},
    "assault_rifle": {"name": "تفنگ تهاجمی", "kind": "weapon", "category": "firearm", "price": 1800, "attack": 30, "defense": 0, "rarity": "حماسی"},
    "battle_rifle": {"name": "تفنگ نبرد", "kind": "weapon", "category": "firearm", "price": 2400, "attack": 36, "defense": 0, "rarity": "حماسی"},
    "pump_shotgun": {"name": "تفنگ ساچمه‌ای", "kind": "weapon", "category": "firearm", "price": 1400, "attack": 26, "defense": 0, "rarity": "کمیاب"},
    "marksman_rifle": {"name": "تفنگ تک‌تیرانداز", "kind": "weapon", "category": "firearm", "price": 2600, "attack": 40, "defense": 0, "rarity": "حماسی"},
    "longshot_rifle": {"name": "تفنگ دوربرد", "kind": "weapon", "category": "firearm", "price": 3300, "attack": 47, "defense": 0, "rarity": "افسانه‌ای"},
    "royal_carbine": {"name": "کارابین سلطنتی", "kind": "weapon", "category": "firearm", "price": 3900, "attack": 53, "defense": 0, "rarity": "افسانه‌ای"},
    "plasma_rifle": {"name": "تفنگ پلاسما (تخیلی)", "kind": "weapon", "category": "firearm", "price": 5200, "attack": 62, "defense": 0, "rarity": "افسانه‌ای"},
    "leather_armor": {"name": "زره چرمی", "kind": "armor", "price": 200, "attack": 0, "defense": 5, "rarity": "معمولی"},
    "chainmail": {"name": "زره زنجیری", "kind": "armor", "price": 650, "attack": 0, "defense": 12, "rarity": "کمیاب"},
    "shadow_armor": {"name": "زره سایه", "kind": "armor", "price": 1500, "attack": 0, "defense": 25, "rarity": "حماسی"},
    "royal_armor": {"name": "زره سلطنتی", "kind": "armor", "price": 3500, "attack": 0, "defense": 45, "rarity": "افسانه‌ای"},
}
BOX_PRICE = 250


def item_stats(weapon_key: str | None, armor_key: str | None) -> dict[str, int]:
    weapon = ITEMS.get(weapon_key or "", {})
    armor = ITEMS.get(armor_key or "", {})
    return {"attack": int(weapon.get("attack", 0)), "defense": int(armor.get("defense", 0))}


def roll_box_reward(rng=None) -> dict:
    """In-game coin-only reward box. Probabilities total 100%; no real-money purchases."""
    rng = rng or random
    roll = rng.randint(1, 100)
    if roll <= 25:
        return {"type": "coins", "key": "coins_80", "amount": 80, "item_key": None}
    if roll <= 50:
        return {"type": "coins", "key": "coins_150", "amount": 150, "item_key": None}
    if roll <= 70:
        return {"type": "coins", "key": "coins_300", "amount": 300, "item_key": None}
    common_items = [k for k, v in ITEMS.items() if v["rarity"] == "معمولی"]
    rare_items = [k for k, v in ITEMS.items() if v["rarity"] in {"کمیاب", "حماسی"}]
    legendary_items = [k for k, v in ITEMS.items() if v["rarity"] == "افسانه‌ای"]
    if roll <= 90:
        key = rng.choice(common_items)
    elif roll <= 98:
        key = rng.choice(rare_items)
    else:
        key = rng.choice(legendary_items)
    return {"type": "item", "key": key, "amount": 1, "item_key": key}
