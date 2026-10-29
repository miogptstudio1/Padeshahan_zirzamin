import unittest
from types import SimpleNamespace
from membership_core import REQUIRED_CHANNELS, membership_status

class FakeBot:
    def __init__(self, statuses):
        self.statuses = statuses
    async def get_chat_member(self, chat_id, user_id):
        status = self.statuses.get(chat_id, "left")
        return SimpleNamespace(status=status, is_member=(status == "restricted"))

class RequiredMembershipTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_channels_required(self):
        bot = FakeBot({"@miogptstudio": "member", "@shady_garden": "member"})
        joined, missing, error = await membership_status(bot, 123)
        self.assertTrue(joined)
        self.assertEqual(missing, [])
        self.assertFalse(error)

    async def test_missing_one_channel_blocks(self):
        bot = FakeBot({"@miogptstudio": "member", "@shady_garden": "left"})
        joined, missing, error = await membership_status(bot, 123)
        self.assertFalse(joined)
        self.assertEqual(missing, ["@shady_garden"])
        self.assertFalse(error)

    async def test_restricted_member_accepted_only_when_member(self):
        bot = FakeBot({"@miogptstudio": "restricted", "@shady_garden": "member"})
        joined, _, _ = await membership_status(bot, 123)
        self.assertTrue(joined)

    def test_required_channels_are_configured(self):
        urls = [channel[2] for channel in REQUIRED_CHANNELS]
        self.assertIn("https://t.me/miogptstudio", urls)
        self.assertIn("https://t.me/shady_garden", urls)

if __name__ == "__main__":
    unittest.main()
