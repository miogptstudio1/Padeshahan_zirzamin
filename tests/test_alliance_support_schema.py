import unittest
from pydantic import ValidationError
from api.schemas import SupportAllianceWarRequest
from games.empire.season_rules import current_season_key, defense_bonus_for_coins
from datetime import datetime, timezone

class AllianceSupportSchemaTests(unittest.TestCase):
    def test_valid_support_amount(self):
        self.assertEqual(SupportAllianceWarRequest(coins=10).coins, 10)
        self.assertEqual(SupportAllianceWarRequest(coins=1000).coins, 1000)
        self.assertEqual(defense_bonus_for_coins(1000), 100)
        self.assertEqual(defense_bonus_for_coins(19), 1)

    def test_support_amount_bounds(self):
        for value in (0, 9, 1001, -10):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    SupportAllianceWarRequest(coins=value)

    def test_season_quarters(self):
        cases = [(1, '2026-Q1'), (3, '2026-Q1'), (4, '2026-Q2'),
                 (6, '2026-Q2'), (7, '2026-Q3'), (9, '2026-Q3'),
                 (10, '2026-Q4'), (12, '2026-Q4')]
        for month, expected in cases:
            with self.subTest(month=month):
                self.assertEqual(current_season_key(datetime(2026, month, 15, tzinfo=timezone.utc)), expected)

if __name__ == '__main__':
    unittest.main()
