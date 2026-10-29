import unittest
from pydantic import ValidationError
from api.schemas import AllianceTreasuryTransferRequest
from games.empire.alliance_economy_rules import DAILY_REWARD, MIN_TRANSFER, MAX_TRANSFER, validate_transfer_amount, war_loot_for_price

class AllianceTreasurySchemaTests(unittest.TestCase):
    def test_transfer_bounds_are_inclusive(self):
        self.assertEqual(AllianceTreasuryTransferRequest(amount=MIN_TRANSFER).amount, MIN_TRANSFER)
        self.assertEqual(AllianceTreasuryTransferRequest(amount=MAX_TRANSFER).amount, MAX_TRANSFER)

    def test_transfer_rejects_out_of_range_amounts(self):
        for amount in (0, 9, 10001, -10):
            with self.subTest(amount=amount):
                with self.assertRaises(ValidationError):
                    AllianceTreasuryTransferRequest(amount=amount)

    def test_daily_reward_is_fixed(self):
        self.assertEqual(DAILY_REWARD, 50)

    def test_service_amount_validation(self):
        self.assertEqual(validate_transfer_amount(10), 10)
        with self.assertRaises(ValueError):
            validate_transfer_amount(10001)

    def test_war_loot_formula(self):
        self.assertEqual(war_loot_for_price(100), 25)
        self.assertEqual(war_loot_for_price(500), 50)
        self.assertEqual(war_loot_for_price(8000), 800)
        with self.assertRaises(ValueError):
            war_loot_for_price(-1)

if __name__ == '__main__':
    unittest.main()
