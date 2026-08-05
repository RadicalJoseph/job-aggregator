import unittest

import aggregator


class MatchesTargetRoleTests(unittest.TestCase):
    def test_matches_broader_role_titles(self):
        self.assertTrue(aggregator.matches_target_role("Director of Technology Services and Projects"))
        self.assertTrue(aggregator.matches_target_role("AI Enablement Lead"))
        self.assertTrue(aggregator.matches_target_role("Senior Manager Science Data & Knowledge Mgmt"))
        self.assertTrue(aggregator.matches_target_role("Sr. Tech Specialist"))


if __name__ == "__main__":
    unittest.main()
