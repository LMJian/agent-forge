"""Exercise the scorer with explicit synthetic good/bad outputs, not model predictions."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_behavior import CASES, score


class BehaviorEvaluation(unittest.TestCase):
    def setUp(self):
        self.cases = json.loads(CASES.read_text())

    def output(self, case):
        return {"claims": [{"text": " ".join(x["terms"]), "status": x["status"], "current": x["current"], "source_ids": x["source_ids"]}
                           for x in case["expected_facts"]],
                "report": " ".join(case["report_required"]), "conflicts": case.get("expected_conflicts", []),
                "stop_reason": case.get("stop_reason"),
                "trace": [{"argv": ["lark-cli", "im", "+messages-search"] if s["kind"] == "message" else ["lark-cli", "docs", "+search"],
                           "source_id": s["id"], "observed_text": s["text"]} for s in case["sources"]]}

    def test_all_golden_outputs_pass_and_record_costs(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                result = score(case, self.output(case))
                self.assertTrue(result["passed"], result["errors"])
                self.assertGreater(result["metrics"]["observed_chars"], 0)

    def test_each_case_detects_its_meaningful_failure(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                output = self.output(case)
                if case["id"] in ("chat-only", "replacement-and-prehistory"):
                    output["claims"][-1]["status"] = "operating"
                elif case["id"] == "new-draft-is-not-decision":
                    output["conflicts"] = []
                elif case["id"] == "low-yield-stop":
                    output["stop_reason"] = "continue"
                else:
                    output["trace"].extend([{"argv": ["lark-cli", "docs", "+create"]}] * 2)
                self.assertFalse(score(case, output)["passed"])

    def test_unknown_anchors_and_remote_writes_fail_read_only_case(self):
        case = self.cases[0]
        output = self.output(case)
        output["claims"][0]["source_ids"] = ["invented"]
        output["trace"].append({"argv": ["lark-cli", "im", "+send"]})
        self.assertGreaterEqual(len(score(case, output)["errors"]), 2)

    def test_export_hides_expectations_from_future_executor(self):
        result = subprocess.run([sys.executable, str(CASES.parents[2] / "scripts" / "evaluate_behavior.py"),
                                 "export", "--case", "chat-only"], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual({"id", "prompt", "sources"}, set(json.loads(result.stdout)))


if __name__ == "__main__":
    unittest.main()
