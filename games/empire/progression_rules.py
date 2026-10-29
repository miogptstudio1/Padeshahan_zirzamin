"""Pure rules for daily/weekly missions and one-time achievements."""
from __future__ import annotations

MISSIONS = {
    "daily": [
        {"key": "daily_army", "title": "آماده‌باش ارتش", "description": "حداقل ۵ سرباز داشته باش.", "stat": "soldiers", "target": 5, "coins": 60, "xp": 20},
        {"key": "daily_territory", "title": "فرمانروای قلمرو", "description": "حداقل یک قلمرو در اختیار داشته باش.", "stat": "cities_owned", "target": 1, "coins": 75, "xp": 25},
        {"key": "daily_economy", "title": "ذخیرهٔ سکه", "description": "موجودی‌ات به ۵۰۰ سکه برسد.", "stat": "coins", "target": 500, "coins": 50, "xp": 15},
    ],
    "weekly": [
        {"key": "weekly_games", "title": "حضور در میدان", "description": "حداقل ۳ بازی انجام داده باش.", "stat": "games_played", "target": 3, "coins": 180, "xp": 60},
        {"key": "weekly_wins", "title": "پیروزی هفتگی", "description": "حداقل یک پیروزی ثبت کرده باش.", "stat": "wins", "target": 1, "coins": 220, "xp": 70},
        {"key": "weekly_soldiers", "title": "ارتش آماده", "description": "حداقل ۲۰ سرباز داشته باش.", "stat": "soldiers", "target": 20, "coins": 200, "xp": 65},
    ],
}

ACHIEVEMENTS = [
    {"key": "first_city", "title": "نخستین قلمرو", "description": "مالک حداقل یک قلمرو شو.", "stat": "cities_owned", "target": 1, "coins": 100, "xp": 40},
    {"key": "five_cities", "title": "فرمانروای بزرگ", "description": "مالک ۵ قلمرو شو.", "stat": "cities_owned", "target": 5, "coins": 700, "xp": 200},
    {"key": "first_win", "title": "اولین پیروزی", "description": "یک پیروزی ثبت کن.", "stat": "wins", "target": 1, "coins": 150, "xp": 50},
    {"key": "ten_wins", "title": "قهرمان میدان", "description": "۱۰ پیروزی ثبت کن.", "stat": "wins", "target": 10, "coins": 1000, "xp": 300},
    {"key": "veteran", "title": "کهنه‌سرباز", "description": "۱۰ بازی انجام بده.", "stat": "games_played", "target": 10, "coins": 500, "xp": 150},
    {"key": "army_100", "title": "ارتش صدنفره", "description": "۱۰۰ سرباز داشته باش.", "stat": "soldiers", "target": 100, "coins": 600, "xp": 180},
]

def period_key(kind: str, date_string: str) -> str:
    if kind not in {"daily", "weekly"}:
        raise ValueError("نوع دوره نامعتبر است")
    return date_string

def mission_progress(mission: dict, stats: dict) -> dict:
    current = max(0, int(stats.get(mission["stat"], 0)))
    target = int(mission["target"])
    return {**mission, "progress": min(current, target), "complete": current >= target}

def level_for_xp(xp: int) -> int:
    return max(1, int(xp) // 100 + 1)
