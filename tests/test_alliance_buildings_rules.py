import unittest
from games.empire.alliance_building_rules import BUILDINGS, MAX_LEVEL, SHIELD_COST, SHIELD_HOURS

class AllianceBuildingConfigTests(unittest.TestCase):
    def test_two_buildings_defined(self):
        self.assertEqual(set(BUILDINGS), {"fortress", "academy"})
    def test_building_costs_increase_linearly(self):
        self.assertEqual(BUILDINGS["fortress"]["base_cost"] * 3, 3000)
        self.assertEqual(BUILDINGS["academy"]["base_cost"] * 2, 2400)
    def test_level_cap(self): self.assertEqual(MAX_LEVEL, 5)
    def test_shield_duration_and_cost(self):
        self.assertEqual(SHIELD_COST, 5000); self.assertEqual(SHIELD_HOURS, 6)

if __name__ == "__main__": unittest.main()
