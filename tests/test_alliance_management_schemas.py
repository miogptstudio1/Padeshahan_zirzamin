import unittest
from pydantic import ValidationError
from api.schemas import (
    TransferLeadershipRequest, KickAllianceMemberRequest, AllianceMessageRequest,
    AlliancePactRequest, DecideAlliancePactRequest,
)

class AllianceManagementSchemaTests(unittest.TestCase):
    def test_transfer_requires_positive_member_id(self):
        self.assertEqual(TransferLeadershipRequest(new_leader_id=42).new_leader_id, 42)
        with self.assertRaises(ValidationError):
            TransferLeadershipRequest(new_leader_id=0)

    def test_kick_requires_positive_id(self):
        with self.assertRaises(ValidationError):
            KickAllianceMemberRequest(telegram_id=-4)

    def test_message_length(self):
        self.assertEqual(AllianceMessageRequest(message='سلام').message, 'سلام')
        with self.assertRaises(ValidationError):
            AllianceMessageRequest(message=' ' * 501)

    def test_pact_requires_positive_alliance_id(self):
        with self.assertRaises(ValidationError):
            AlliancePactRequest(alliance_id=0)

    def test_decision_requires_boolean(self):
        self.assertTrue(DecideAlliancePactRequest(accept=True).accept)

if __name__ == '__main__':
    unittest.main()
