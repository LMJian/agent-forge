"""Codex's short route, technical-risk gate and acceptance ledger through real CLI/Git/checks."""
import copy
from pathlib import Path
import sys

from harness import guidance, runner
from harness.engine import Workflow
from harness.model import HarnessError, default_config, resolve_workflow
from harness.quality import progress, record_body
from harness.reuse import reuse
from harness.storage import atomic_json, read_json
from harness.verification import verify
import test_host_execution as support
from test_workflow import RepoCase


class CodexFlowTests(RepoCase):
    cli = support.PortableExecutionTests.cli

    def setUp(self):
        super().setUp()
        self.flow.abort("Use the new Codex route")
        config = read_json(self.root / ".harness/project.json")
        config["workflow"] = {"profile": "codex", "isolation": "checkout"}
        config["adapters"] = {}
        config["stage_checks"] = {"review": ["unit"], "integration": ["unit"]}
        config["checks"]["unit"]["reuse"] = {
            "context_files": [], "max_age_seconds": 7200, "across_stages": True,
            "assumptions": "Offline deterministic Python behavior; no stage, Git or external state inputs"}
        config["checks"]["unit"]["proof"] = "runtime"
        atomic_json(self.root / ".harness/project.json", config)
        self.commit("Configure Codex local route")
        self.flow = Workflow(self.root, "codex")
        self.cli("start", "--goal", "Implement and verify the public value behavior")
        self.artifact = self.write(".harness/runs/codex/artifacts/decision.md", "Observable value=2; retain old value=1.\n")
        self.details = {"acceptance": ["AC-1"], "modules": [{"id": "core", "acceptance": ["AC-1"]}],
                        "approach": "Add a pure public value function", "verification": "Exercise the public behavior",
                        "journey": {"entry": "Call the public value API", "terminal_outcome": "Caller receives 2",
                                    "steps": [{"id": "value", "outcome": "Public value is 2", "proof": "runtime", "acceptance": ["AC-1"]}]},
                        "feasibility": {"assessment": "Known local Python runtime, no novel algorithm or device dependency", "risks": []},
                        "tasks": {"core": [{"id": "build", "summary": "Implement public behavior", "acceptance": ["AC-1"],
                                            "verification": "Call value and assert 2"}]},
                        "scenarios": [{"id": "value", "acceptance": ["AC-1"], "executor": "command", "check": "unit",
                                       "level": "product", "proof": "runtime", "steps": ["value"],
                                       "oracle": "API requirement specifies 2, independently of its implementation", "environment": "Local Python process",
                                       "procedure": "Invoke public value function", "expected": "Returns 2, retains base value=1"}]}

    def body(self, name, **extra):
        path = self.root / f".harness/runs/codex/artifacts/{name}.json"
        atomic_json(path, {"status": "pass", "summary": name, "artifacts": [str(self.artifact)], "findings": [], **extra})
        return path

    def intake(self):
        return self.cli("submit", "--result", str(self.body("intake", details=self.details)))

    def implement(self):
        self.intake()
        packet = self.cli("next")
        self.assertEqual(packet["stage"], "implement")
        self.assertEqual(packet["action"]["kind"], "prepare_module")
        _, receipt = self.implement_module()
        self.verify_module("core", receipt)
        self.cli("submit", "--result", str(self.body("implement")))
        self.cli("next")
        return receipt

    def manual(self):
        case = copy.deepcopy(self.details["scenarios"][0])
        case.update(id="appearance", executor="human", reason="Subjective visual judgment after automated behavior checks", batch="final-look")
        case.pop("check")
        self.details["scenarios"].append(case)

    def result(self, status="passed", **extra):
        return {"case": "appearance", "status": status, "summary": "Actual observed outcome",
                "artifacts": [str(self.artifact)], **extra}

    def test_default_is_short_codex_route_and_autonomous(self):
        cfg = default_config()
        flow = resolve_workflow(cfg)
        self.assertEqual(flow["profile"], "codex")
        self.assertEqual(flow["assistance"], "autonomous")
        self.assertEqual(flow["isolation"], "checkout")
        self.assertEqual([s for s in flow["order"] if flow["enabled"][s]], ["intake", "plan", "implement", "review"])

    def test_public_cli_finishes_with_one_execution_across_three_stages(self):
        first = self.implement()
        review = self.cli("verify")
        self.assertEqual((review["executed"], review["reused"]), (0, 1))
        self.assertEqual(review["checks"][0]["reused_from"], first["id"])
        self.assertEqual(self.cli("test-progress")["passed"], 1)
        self.cli("submit", "--result", str(self.body("review")))
        integration = self.cli("verify")
        self.assertEqual((integration["executed"], integration["reused"]), (0, 1))
        result = self.cli("submit", "--result", str(self.body("integration")))
        self.assertEqual(result["status"], "complete")
        runs = self.flow.load()["runs"]
        self.assertEqual(sum(not r.get("reused_from") for r in runs), 1)
        self.assertEqual(self.cli("next")["action"]["kind"], "finished")
        self.write("feature_core.py", "def value():\n    return 3\n")
        # Finished state is not enough after the verified code changes.
        self.assertEqual(self.cli("next")["action"]["kind"], "repair_evidence")

    def test_critical_unproven_algorithm_cannot_reach_implementation(self):
        self.details["feasibility"]["risks"] = [{"id": "alignment", "critical": True,
              "assumption": "Real captured frames align reliably", "status": "unproven"}]
        result = self.cli("submit", "--result", str(self.body("risk", details=self.details)), expected=2)
        self.assertIn("Critical feasibility", str(result))
        self.assertFalse(self.flow.load()["modules"])

    def test_critical_probe_requires_execution_and_observed_artifact(self):
        self.cli("next")
        probe = self.cli("run-check", "unit")
        self.details["feasibility"]["risks"] = [{"id": "runtime", "critical": True,
            "assumption": "Baseline public entry works in selected runtime", "status": "proven",
            "experiment": "Execute baseline public value test", "expected": "value=1", "observed": "Test passed",
            "evidence": [str(self.artifact)], "checks": [probe["id"]]}]
        self.intake()
        self.assertEqual(self.cli("next")["stage"], "implement")

    def test_fake_probe_receipt_rejected(self):
        self.details["feasibility"]["risks"] = [{"id": "runtime", "critical": True, "assumption": "Supported",
            "status": "proven", "experiment": "Probe", "expected": "Pass", "observed": "Claim",
            "evidence": [str(self.artifact)], "checks": ["not-executed"]}]
        result = self.cli("submit", "--result", str(self.body("fake", details=self.details)), expected=2)
        self.assertIn("actual successful", str(result))

    def test_unit_only_coverage_is_not_product_acceptance(self):
        self.details["scenarios"][0]["level"] = "component"
        result = self.cli("submit", "--result", str(self.body("unit-only", details=self.details)), expected=2)
        self.assertIn("product-level", str(result))

    def test_missing_terminal_side_effect_scenario_blocks_intake(self):
        self.details["journey"]["terminal_outcome"] = "Image is saved in Photos"
        self.details["journey"]["steps"].append({"id": "save", "outcome": "Read back saved image", "proof": "runtime", "acceptance": ["AC-1"]})
        result = self.cli("submit", "--result", str(self.body("missing-save", details=self.details)), expected=2)
        self.assertIn("untested steps", str(result))
        self.assertFalse(self.flow.load()["modules"])

    def test_artifact_replay_cannot_prove_native_runtime_even_if_named_product(self):
        config = read_json(self.root / ".harness/project.json")
        config["checks"]["unit"]["proof"] = "artifact"
        atomic_json(self.root / ".harness/project.json", config)
        self.flow.sync_config("Fixture replay only examines saved files")
        self.details["scenarios"][0]["proof"] = "artifact"
        result = self.cli("submit", "--result", str(self.body("wrong-boundary", details=self.details)), expected=2)
        self.assertIn("cannot prove a runtime", str(result))

    def test_build_check_cannot_masquerade_as_runtime(self):
        config = read_json(self.root / ".harness/project.json")
        config["checks"]["unit"]["proof"] = "build"
        atomic_json(self.root / ".harness/project.json", config)
        self.flow.sync_config("Fixture has build evidence only")
        result = self.cli("submit", "--result", str(self.body("build-only", details=self.details)), expected=2)
        self.assertIn("check boundary", str(result))

    def test_current_module_reuses_unchanged_inputs_and_fresh_forces_execution(self):
        self.intake()
        self.cli("next")
        _, first = self.implement_module()
        before = len(self.flow.load()["runs"])
        planned = self.cli("verify-plan", "--module", "core")
        self.assertEqual(len(self.flow.load()["runs"]), before)
        self.assertEqual(planned["checks"][0]["reuse_from"], first["id"])
        self.assertEqual(planned["estimated_seconds"], 0)
        result = self.cli("verify", "--module", "core")
        self.assertEqual((result["executed"], result["reused"]), (0, 1))
        result = self.cli("verify", "--module", "core", "--fresh")
        self.assertEqual((result["executed"], result["reused"]), (1, 0))

    def test_critical_failure_runs_before_broad_regression_and_stops_batch(self):
        config = read_json(self.root / ".harness/project.json")
        config["checks"]["entry-smoke"] = {"argv": [sys.executable, "-c", "raise SystemExit(1)"], "tier": "critical", "proof": "runtime"}
        config["stage_checks"]["review"].append("entry-smoke")
        atomic_json(self.root / ".harness/project.json", config)
        self.flow.sync_config("Run the real entry gate first in the fixture")
        self.intake()
        self.cli("next")
        self.cli("prepare-module", "core")
        planned = self.cli("verify-plan", "--module", "core")
        self.assertEqual([c["name"] for c in planned["checks"]], ["entry-smoke", "unit"])
        result = self.cli("verify", "--module", "core", expected=1)
        self.assertEqual([c["name"] for c in result["checks"]], ["entry-smoke"])
        self.assertEqual(result["remaining"], ["unit"])

    def test_post_delivery_failure_invalidates_green_completion(self):
        self.implement()
        self.cli("verify")
        self.cli("submit", "--result", str(self.body("review")))
        self.cli("verify")
        self.cli("submit", "--result", str(self.body("integration")))
        self.assertEqual(self.cli("next")["action"]["kind"], "finished")
        record_body(self.flow, {"case": "value", "status": "failed", "summary": "User observes incorrect public output",
                               "actor": "user", "authorization": "Fixture reports value is wrong", "artifacts": [str(self.artifact)]})
        self.assertEqual(self.cli("test-progress")["failed"], 1)
        self.assertEqual(self.cli("next")["action"]["kind"], "repair_evidence")

    def test_human_case_requires_reason_and_batch(self):
        self.manual()
        del self.details["scenarios"][1]["reason"]
        result = self.cli("submit", "--result", str(self.body("manual", details=self.details)), expected=2)
        self.assertIn("human scenario.reason", str(result))

    def test_approval_uses_single_packet_and_stops_before_plan(self):
        self.flow.configure_flow({"stages": {"design_approval": True}}, "User requested design approval")
        self.intake()
        packet = self.cli("next")
        self.assertEqual(packet["action"]["kind"], "approval")
        self.assertFalse(self.flow.load()["modules"])
        with self.assertRaises(HarnessError):
            self.flow.enter("implement")
        self.cli("approve", "design_approval", "--actor", "user", "--note", "Approve the actual decision packet")
        self.assertEqual(self.cli("next")["stage"], "implement")

    def test_missing_or_blocked_manual_case_blocks_review_and_counts_once(self):
        self.manual()
        self.implement()
        self.cli("verify")
        p = self.cli("test-progress")
        self.assertEqual((p["total"], p["remaining"], p["human_remaining"], p["human_batches"]), (2, 1, 1, ["final-look"]))
        result = self.cli("submit", "--result", str(self.body("review")), expected=2)
        self.assertIn("Acceptance incomplete", str(result))
        record_body(self.flow, self.result("blocked"))
        record_body(self.flow, self.result("blocked"))
        self.assertEqual(self.cli("test-progress")["blocked"], 1)

    def test_waiver_requires_actual_decision_and_is_not_a_pass(self):
        self.manual()
        self.implement()
        self.cli("verify")
        with self.assertRaisesRegex(HarnessError, "actual user"):
            record_body(self.flow, self.result("waived"))
        with self.assertRaisesRegex(HarnessError, "authorization"):
            record_body(self.flow, self.result("waived", actor="user"))
        record_body(self.flow, self.result("waived", actor="user", authorization="Do not test subjective appearance in this batch"))
        p = self.cli("test-progress")
        self.assertEqual((p["passed"], p["waived"], p["remaining"]), (1, 1, 0))
        self.cli("submit", "--result", str(self.body("review")))

    def test_false_command_pass_and_human_attestation_are_rejected(self):
        self.manual()
        self.implement()
        with self.assertRaisesRegex(HarnessError, "actual successful"):
            record_body(self.flow, {**self.result(), "case": "value", "check": "fake"})
        with self.assertRaisesRegex(HarnessError, "actual user"):
            record_body(self.flow, self.result())

    def test_code_change_stales_acceptance_instead_of_reusing_green_counts(self):
        self.implement()
        self.cli("verify")
        self.write("feature_core.py", "def value():\n    return 99\n")
        self.assertEqual(self.cli("test-progress")["stale"], 1)

    def test_failed_command_is_not_recorded_as_pass(self):
        self.implement()
        # Additional failing test changes the final bytes; repair through the supported stage path.
        self.flow.reopen("implement", "Observe product regression")
        guidance.advance(self.flow)
        self.write("tests/test_failure.py", "import unittest\nclass Failure(unittest.TestCase):\n def test_failure(self):\n  self.fail('product broken')\n")
        self.flow.reopen("plan", "Replan final verification against failing code")
        guidance.advance(self.flow)
        from harness import worktrees
        worktrees.prepare(self.flow, "core")
        result = verify(self.flow, "core", fresh=True)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(progress(self.flow, self.flow.load())["passed"], 0)

    def test_fresh_flag_runs_again_even_when_reuse_is_possible(self):
        self.implement()
        result = self.cli("verify", "--fresh")
        self.assertEqual((result["executed"], result["reused"]), (1, 0))

    def test_cross_stage_reuse_needs_explicit_policy(self):
        config = read_json(self.root / ".harness/project.json")
        del config["checks"]["unit"]["reuse"]["across_stages"]
        atomic_json(self.root / ".harness/project.json", config)
        self.flow.sync_config("Use legacy review-only reuse policy")
        first = self.implement()
        with self.assertRaises(HarnessError):
            reuse(self.flow, "unit", first["id"])
        self.assertEqual(self.cli("verify")["executed"], 1)

    def test_invalid_tasks_are_rejected_before_intake_advances(self):
        self.details["tasks"]["core"][0]["acceptance"] = ["unknown"]
        result = self.cli("submit", "--result", str(self.body("bad-plan", details=self.details)), expected=2)
        self.assertIn("unknown module acceptance", str(result))
        self.assertEqual(self.flow.status()["current_stage"], "intake")

    def test_existing_light_task_requires_new_packet_when_opting_into_codex(self):
        self.flow.configure_flow({"profile": "light"}, "Existing task policy")
        self.intake()
        self.flow.configure_flow({"profile": "codex"}, "User adopts the new evidence contract")
        self.assertEqual(self.flow.status()["current_stage"], "intake")
        self.assertFalse(self.flow.load()["modules"])

    def test_deleted_intake_report_is_reported_stale_without_crashing_status(self):
        self.intake()
        state = self.flow.load()
        (self.root / state["stages"]["intake"]["report"]).unlink()
        result = self.cli("status")
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["test_progress"]["status"], "unavailable")

    def test_stale_probe_cannot_prove_feasibility(self):
        self.cli("next")
        probe = self.cli("run-check", "unit")
        self.write("changed.py", "changed = True\n")
        self.details["feasibility"]["risks"] = [{"id": "runtime", "critical": True,
            "assumption": "Runtime works", "status": "proven", "experiment": "Baseline test",
            "expected": "Pass", "observed": "Pass", "evidence": [str(self.artifact)], "checks": [probe["id"]]}]
        result = self.cli("submit", "--result", str(self.body("stale-probe", details=self.details)), expected=2)
        self.assertIn("stale", str(result))

    def test_verify_records_real_failure_and_stops_without_a_green_case(self):
        control = self.write(".harness/runs/codex/control", "pass")
        config = read_json(self.root / ".harness/project.json")
        config["checks"]["unit"]["argv"] = [sys.executable, "-c", "from pathlib import Path; assert Path('.harness/runs/codex/control').read_text() == 'pass'"]
        config["checks"]["unit"]["reuse"]["context_files"] = [".harness/runs/codex/control"]
        atomic_json(self.root / ".harness/project.json", config)
        self.flow.sync_config("Exercise a real failing command")
        self.implement()
        control.write_text("fail")
        result = self.cli("verify", "--fresh", expected=1)
        self.assertEqual(result["status"], "failed")
        counts = self.cli("test-progress")
        self.assertEqual((counts["failed"], counts["passed"], counts["remaining"]), (1, 0, 1))
