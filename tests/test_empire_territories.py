import unittest
from games.empire.engine import CITIES, MAX_DEFENSE_LEVEL, defense_upgrade_cost, city_tax

class EmpireTerritoryTests(unittest.TestCase):
    def test_five_cities_defined(self):
        self.assertEqual(len(CITIES), 5)
        self.assertEqual(CITIES['capital']['price'], 8000)
    def test_defense_cost_increases_by_level(self):
        self.assertEqual(defense_upgrade_cost('market', 0), 250)
        self.assertEqual(defense_upgrade_cost('market', 1), 500)
    def test_defense_max_level_rejected(self):
        with self.assertRaises(ValueError): defense_upgrade_cost('port', MAX_DEFENSE_LEVEL)
    def test_city_tax_values(self):
        self.assertEqual(city_tax('capital'), 500)
        with self.assertRaises(ValueError): city_tax('unknown')

if __name__ == '__main__': unittest.main()
