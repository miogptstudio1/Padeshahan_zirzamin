import unittest
from games.empire.alliance_governance_rules import validate_proposal
from api.schemas import AllianceProposalRequest, AllianceVoteRequest

class AllianceGovernanceTests(unittest.TestCase):
    def test_valid_proposal_is_normalized(self):
        self.assertEqual(validate_proposal('  ساخت آکادمی  ', '  باید قدرت حمله بیشتر شود  ', 24),
                         ('ساخت آکادمی', 'باید قدرت حمله بیشتر شود', 24))

    def test_title_bounds(self):
        with self.assertRaises(ValueError):
            validate_proposal('کم', 'این توضیح به اندازه کافی طولانی است', 24)
        with self.assertRaises(ValueError):
            validate_proposal('ع' * 101, 'این توضیح به اندازه کافی طولانی است', 24)

    def test_description_bounds(self):
        with self.assertRaises(ValueError):
            validate_proposal('عنوان مناسب', 'کوتاه', 24)

    def test_duration_bounds(self):
        for duration in (0, 73, True):
            with self.assertRaises(ValueError):
                validate_proposal('عنوان مناسب', 'این توضیح به اندازه کافی طولانی است', duration)

    def test_request_schemas(self):
        self.assertEqual(AllianceProposalRequest(title='عنوان مناسب', description='توضیح کافی برای پیشنهاد', duration_hours=6).duration_hours, 6)
        self.assertEqual(AllianceVoteRequest(choice='yes').choice, 'yes')
        with self.assertRaises(Exception):
            AllianceVoteRequest(choice='maybe')
        with self.assertRaises(Exception):
            AllianceProposalRequest(title='کم', description='توضیح کافی برای پیشنهاد')

if __name__ == '__main__':
    unittest.main()
