import unittest
from games.empire.engine import ASSETS, asset_cost, hourly_income, can_collect, MAX_ASSET_LEVEL, COLLECT_COOLDOWN_SECONDS

class EmpireEngineTests(unittest.TestCase):
    def test_initial_purchase_costs(self):
        self.assertEqual(asset_cost('workshop', 0), 100)
        self.assertEqual(asset_cost('club', 0), 250)
        self.assertEqual(asset_cost('factory', 0), 500)

    def test_upgrade_cost_increases_by_level(self):
        self.assertEqual(asset_cost('workshop', 1), 200)
        self.assertEqual(asset_cost('factory', 4), 2500)

    def test_max_level_cannot_be_upgraded(self):
        with self.assertRaises(ValueError):
            asset_cost('club', MAX_ASSET_LEVEL)

    def test_hourly_income_scales_with_level(self):
        self.assertEqual(hourly_income('workshop', 1), 15)
        self.assertEqual(hourly_income('workshop', 3), 45)
        self.assertEqual(hourly_income('factory', 5), 400)

    def test_collection_available_for_new_asset(self):
        self.assertTrue(can_collect(None, 1000))

    def test_collection_cooldown(self):
        self.assertFalse(can_collect(1000, 1000 + COLLECT_COOLDOWN_SECONDS - 1))
        self.assertTrue(can_collect(1000, 1000 + COLLECT_COOLDOWN_SECONDS))

    def test_unknown_asset_rejected(self):
        with self.assertRaises(ValueError):
            asset_cost('palace', 0)
        with self.assertRaises(ValueError):
            hourly_income('palace', 1)

if __name__ == '__main__':
    unittest.main()
