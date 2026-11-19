"""Preserve mandatory policy text and replayable cases; not an agent permission engine."""
import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AgentRulesTests(unittest.TestCase):
    def section(self, title):
        text = (ROOT / "AGENTS.md").read_text()
        return text.split("## " + title + "\n", 1)[1].split("## ", 1)[0]

    def test_gui_authorization_requirements_are_preserved_verbatim(self):
        actual = hashlib.sha256(self.section("Computer Use authorization — mandatory").encode()).hexdigest()
        self.assertEqual(actual, "9c08ccc2356847604e816514b6dd470a6a756375dd62dd49d9a26e7f19456345")

    def test_branch_authorization_requirements_are_preserved_verbatim(self):
        actual = hashlib.sha256(self.section("Development branch authorization — mandatory").encode()).hexdigest()
        self.assertEqual(actual, "9ab7f692fd8c9f12ff5acb644416b52cd1c53411efe4a8bcf71a2644a05fe645")

    def test_counterexamples_have_distinct_ids_context_requests_and_criteria(self):
        data = json.loads((ROOT / "evals/cases.json").read_text())
        self.assertEqual(data["schema_version"], 1)
        self.assertTrue(data["cases"])
        ids = []
        for case in data["cases"]:
            with self.subTest(case=case.get("id")):
                self.assertEqual(set(case), {"id", "context", "request", "criteria"})
                ids.append(case["id"])
                for key in ("id", "context", "request"):
                    self.assertIsInstance(case[key], str)
                    self.assertTrue(case[key].strip())
                self.assertGreaterEqual(len(case["criteria"]), 2)
                self.assertTrue(all(isinstance(c, str) and c.strip() for c in case["criteria"]))
        self.assertEqual(len(ids), len(set(ids)))

    def test_readme_references_exist(self):
        text = (ROOT / "README.md").read_text()
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            if "://" not in target:
                self.assertTrue((ROOT / target.split("#", 1)[0]).is_file(), target)


if __name__ == "__main__":
    unittest.main()
