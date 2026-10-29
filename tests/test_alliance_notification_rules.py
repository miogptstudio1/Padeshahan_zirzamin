import unittest
from games.empire.alliance_notification_rules import CATEGORIES, validate_preferences

class AllianceNotificationRulesTests(unittest.TestCase):
    def test_expected_categories_exist(self):
        self.assertEqual(set(CATEGORIES), {"treasury", "rank", "war", "buildings", "general"})

    def test_valid_preferences(self):
        result = validate_preferences(False, {"war": False, "treasury": True})
        self.assertFalse(result["telegram_enabled"])
        self.assertFalse(result["categories"]["war"])

    def test_unknown_category_rejected(self):
        with self.assertRaises(ValueError):
            validate_preferences(True, {"secrets": False})

    def test_non_boolean_values_rejected(self):
        with self.assertRaises(ValueError):
            validate_preferences(True, {"war": "off"})

    def test_telegram_flag_must_be_boolean(self):
        with self.assertRaises(ValueError):
            validate_preferences("yes", {})

if __name__ == "__main__":
    unittest.main()
