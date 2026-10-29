import unittest
from api.schemas import AllianceRankRequest

class AllianceRankSchemaTests(unittest.TestCase):
    def test_valid_ranks(self):
        for rank in ('commander', 'treasurer', 'officer', 'member'):
            body = AllianceRankRequest(telegram_id=12345, rank=rank)
            self.assertEqual(body.rank, rank)

    def test_leader_rank_cannot_be_assigned(self):
        with self.assertRaises(Exception):
            AllianceRankRequest(telegram_id=12345, rank='leader')

    def test_invalid_user_id_rejected(self):
        with self.assertRaises(Exception):
            AllianceRankRequest(telegram_id=0, rank='member')

if __name__ == '__main__':
    unittest.main()
