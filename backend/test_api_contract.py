import unittest

from backend.api import health, instagram_status, root


class ApiContractTests(unittest.TestCase):
    def test_health_contract(self):
        response = health()
        self.assertEqual(response["status"], "ready")
        self.assertEqual(response["service"], "geotrace-cyber-pipeline")

    def test_root_points_to_docs_and_health(self):
        response = root()
        self.assertIn(b'"docs":"/docs"', response.body)
        self.assertIn(b'"health":"/health"', response.body)

    def test_instagram_status_has_no_session_material(self):
        response = instagram_status()
        self.assertIn(response["status"], {"active", "disabled"})
        self.assertNotIn("password", response)


if __name__ == "__main__":
    unittest.main()
