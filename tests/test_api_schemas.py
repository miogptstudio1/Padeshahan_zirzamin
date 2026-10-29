import unittest
from pydantic import ValidationError
from api.schemas import DeclareWarRequest, RecruitRequest, CreateAllianceRequest, JoinAllianceRequest, ManageAllianceRequest


class ApiSchemaTests(unittest.TestCase):
    def test_recruit_count_bounds(self):
        self.assertEqual(RecruitRequest(count=5).count, 5)
        for count in (0, 101):
            with self.assertRaises(ValidationError):
                RecruitRequest(count=count)

    def test_alliance_creation_validation(self):
        valid = CreateAllianceRequest(name="نگهبانان شب", tag="N1GHT")
        self.assertEqual(valid.name, "نگهبانان شب")
        self.assertEqual(valid.tag, "N1GHT")
        with self.assertRaises(ValidationError):
            CreateAllianceRequest(name="x", tag="!")

    def test_join_and_manage_alliance_schemas(self):
        self.assertEqual(JoinAllianceRequest(alliance_id=3).alliance_id, 3)
        self.assertTrue(ManageAllianceRequest(accept=True).accept)
        with self.assertRaises(ValidationError):
            JoinAllianceRequest(alliance_id=0)

    def test_war_request_accepts_city_keys(self):
        request = DeclareWarRequest(attack_city_key="market", target_city_key="capital")
        self.assertEqual(request.attack_city_key, "market")
        self.assertEqual(request.target_city_key, "capital")

    def test_war_request_rejects_arbitrary_path_input(self):
        with self.assertRaises(ValidationError):
            DeclareWarRequest(attack_city_key="../users", target_city_key="capital")


if __name__ == "__main__":
    unittest.main()
