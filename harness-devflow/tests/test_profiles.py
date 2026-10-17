"""Task-scoped routes, delivery endpoints and optional isolation with real Git/checks."""
import json
import contextlib
import io
from pathlib import Path
import sys

from harness import knowledge, runner, worktrees
from harness.cli import main
from harness.engine import Workflow
from harness.model import HarnessError, default_config, resolve_workflow, validate_config
from harness.storage import atomic_json, read_json
from test_workflow import RepoCase


class ProfileTests(RepoCase):
    def setUp(self):
        super().setUp()
        config = read_json(self.root / ".harness/project.json")
        config["workflow"] = {"assistance": "autonomous"}
        config["stage_checks"]["integration"] = []
        atomic_json(self.root / ".harness/project.json", config)
        self.commit("Use default workflow policy")
        self.flow.sync_config("Use task-selected profiles")
        self.flow.configure_flow({"profile": "light"}, "Small reversible feature")

    def light_intake(self):
        self.finish("intake", details={"acceptance": ["AC-1"],
                    "modules": [{"id": "core", "acceptance": ["AC-1"]}],
                    "approach": "Extend the existing value function with a focused module",
                    "verification": "Assert the new observable return value in a unit test"})

    def light_review(self):
        self.light_intake()
        self.plan_tasks()
        self.flow.enter("implement")
        wt, receipt = self.implement_module()
        self.assertEqual(wt, self.root)
        self.verify_module("core", receipt)
        self.finish("implement")
        self.flow.enter("review")
        receipt = runner.run(self.flow, "check", "unit")
        return self.flow.complete("review", str(self.report("review", checks=[receipt["id"]])))

    def adapters(self):
        config = read_json(self.root / ".harness/project.json")
        responses = {
            "push": {"summary": "Local push simulation"},
            "pr": {"summary": "Local PR simulation", "external_id": "42", "url": "https://example.test/pr/42"},
            "monitor": {"summary": "Local merge simulation", "state": "merged"},
            "deploy": {"summary": "Local deployment simulation", "deployment_id": "fixture-deploy"},
        }
        for stage, result in responses.items():
            response = {"schema_version": 1, "status": "pass", **result}
            config["adapters"][stage] = {"argv": [sys.executable, "-c", "print(" + repr(json.dumps(response)) + ")"],
                                         "effect": "read" if stage == "monitor" else "external"}
        config["stage_checks"]["integration"] = ["unit"]
        atomic_json(self.root / ".harness/project.json", config)
        self.commit("Configure explicit local provider fixtures")
        self.flow.sync_config("Configure endpoint tests before implementation")
        self.flow.configure_flow({"stages": {"integration": False}}, "No additional suite in this fixture")

    def finish_adapter(self, stage):
        self.flow.enter(stage)
        receipt = runner.run(self.flow, "adapter", stage, authorization="Execute the explicit local test fixture")
        self.assertEqual(receipt["status"], "passed", receipt)
        return self.flow.complete(stage, str(self.report(stage, adapter_run=receipt["id"])))

    def test_light_flow_finishes_locally_without_worktrees_or_human_gates(self):
        result = self.light_review()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["active_stages"], ["intake", "plan", "implement", "review"])
        self.assertFalse((self.root / ".harness/worktrees").exists())
        self.assertFalse(any(e["action"] == "request_approval" for e in self.flow.load()["events"]))
        self.assertTrue((self.root / "feature_core.py").exists())

    def test_compact_intake_still_requires_approach_and_verification(self):
        self.flow.enter("intake")
        report = self.report("intake", details={"acceptance": ["AC-1"],
                              "modules": [{"id": "core", "acceptance": ["AC-1"]}]})
        with self.assertRaisesRegex(HarnessError, "approach"):
            self.flow.complete("intake", str(report))

    def test_planning_requires_actionable_tasks_and_acceptance_coverage(self):
        self.light_intake()
        path = self.root / ".harness/runs/example/artifacts/bad-tasks.json"
        atomic_json(path, {"core": [{"id": "build", "summary": "Build", "verification": "Test", "acceptance": ["unknown"]}]})
        with self.assertRaisesRegex(HarnessError, "unknown module acceptance"):
            self.flow.plan(str(path))
        result = self.plan_tasks()
        self.assertEqual(result["current_stage"], "implement")

    def test_module_report_must_finish_planned_task_ids(self):
        self.light_intake()
        self.plan_tasks()
        self.flow.enter("implement")
        _, receipt = self.implement_module()
        report = self.report("implement", module="core", completed_tasks=["unplanned"],
                             acceptance=["AC-1"], checks=[receipt["id"]])
        with self.assertRaisesRegex(HarnessError, "planned task IDs"):
            worktrees.complete(self.flow, "core", str(report))

    def test_completed_local_pr_merged_and_deployed_endpoints_can_be_extended(self):
        self.adapters()
        self.assertEqual(self.light_review()["status"], "complete")
        original_review = self.flow.load()["stages"]["review"]["epoch"]
        result = self.flow.configure_flow({"target": "pr"}, "Now deliver the verified change for review")
        self.assertEqual(result["current_stage"], "push")
        self.assertEqual(self.flow.load()["stages"]["review"]["epoch"], original_review)
        with self.assertRaises(HarnessError):
            self.flow.skip("push", "Cannot silently remove the selected delivery target")
        self.finish_adapter("push")
        result = self.finish_adapter("pr")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["stages"]["monitor"], "skipped")
        result = self.flow.configure_flow({"target": "merged"}, "Now wait for the PR to merge")
        self.assertEqual(result["current_stage"], "monitor")
        self.assertEqual(self.finish_adapter("monitor")["status"], "complete")
        result = self.flow.configure_flow({"target": "deployed"}, "Now prepare deployment")
        self.assertEqual(result["current_stage"], "release")
        self.flow.enter("release")
        checks = {k: {"status": "pass", "evidence": "Local fixture release evidence"}
                  for k in ("verification", "rollback", "observability", "risks")}
        path = self.report("release", details={"checklist": checks})
        result = self.flow.complete("release", str(path), request_approval=True)
        self.assertEqual(result["status"], "waiting_human")
        with self.assertRaises(HarnessError):
            self.flow.enter("deploy")
        self.flow.approve("release", "fixture", "Approve this local deployment packet")
        self.assertEqual(self.finish_adapter("deploy")["status"], "complete")

    def test_remote_integration_position_is_respected_and_reopen_uses_task_order(self):
        self.adapters()
        self.flow.configure_flow({"target": "pr", "integration_position": "after_push",
                                  "stages": {"integration": True}}, "Test the pushed preview environment")
        self.assertEqual(self.light_review()["current_stage"], "push")
        self.assertEqual(self.finish_adapter("push")["current_stage"], "integration")
        self.flow.enter("integration")
        receipt = runner.run(self.flow, "check", "unit")
        self.flow.complete("integration", str(self.report("integration", checks=[receipt["id"]])))
        result = self.flow.reopen("integration", "Rerun environment verification")
        self.assertEqual(result["stages"]["push"], "done")
        self.assertEqual(result["current_stage"], "integration")

    def test_local_integration_precedes_push_and_reopening_it_invalidates_push(self):
        self.adapters()
        self.flow.configure_flow({"target": "pr", "stages": {"integration": True}}, "Run local suite before delivery")
        self.assertEqual(self.light_review()["current_stage"], "integration")
        self.flow.enter("integration")
        receipt = runner.run(self.flow, "check", "unit")
        self.flow.complete("integration", str(self.report("integration", checks=[receipt["id"]])))
        self.finish_adapter("push")
        result = self.flow.reopen("integration", "Recheck the integration evidence")
        self.assertEqual(result["stages"]["push"], "pending")

    def test_auto_isolation_uses_worktrees_for_multiple_modules(self):
        self.finish("intake", details={"acceptance": ["AC-1"], "approach": "Two independent modules",
                    "verification": "Run module unit tests", "modules": [
                        {"id": "core", "acceptance": ["AC-1"]}, {"id": "api", "acceptance": ["AC-1"]}]})
        self.plan_tasks()
        self.flow.enter("implement")
        info = worktrees.prepare(self.flow, "core")
        self.assertNotEqual(Path(info["worktree"]), self.root)
        self.assertEqual(self.flow.load()["execution_mode"], "worktree")
        with self.assertRaisesRegex(HarnessError, "one module"):
            self.flow.configure_flow({"isolation": "checkout"}, "Try unsupported shared checkout")

    def test_local_knowledge_is_searchable_without_claiming_human_approval(self):
        self.flow.configure_flow({"stages": {"knowledge": True}}, "Retain local implementation notes")
        self.light_review()
        result = self.finish("knowledge", details={"outcome": "draft"})
        self.assertEqual(result["status"], "complete")
        matches = knowledge.search(self.root, "reusable")["results"]
        self.assertTrue(matches)
        self.assertFalse(matches[0]["human_approved"])

    def test_no_changes_needs_no_approval_and_creates_no_knowledge_snapshot(self):
        self.flow.configure_flow({"stages": {"knowledge": True}, "knowledge_approval": True}, "Review reusable notes if any")
        self.light_review()
        result = self.finish("knowledge", details={"outcome": "no_changes"})
        self.assertEqual(result["status"], "complete")
        self.assertFalse((self.root / ".harness/knowledge").exists())

    def test_reopening_core_keeps_excluded_stages_excluded(self):
        self.light_review()
        result = self.flow.reopen("intake", "Change the intended behavior")
        self.assertEqual(result["stages"]["design_approval"], "skipped")
        self.assertEqual(result["stages"]["release"], "skipped")
        self.assertEqual(result["waves"], [])

    def test_changed_plan_after_inline_implementation_requires_replanning(self):
        self.light_review()
        state = self.flow.load()
        plan = self.flow.report_for(state, "plan")
        path = Path(plan["artifacts"][0])
        path.write_text(path.read_text() + "\n")
        self.assertEqual(self.flow.status()["status"], "stale")

    def test_defaults_and_invalid_profile_combinations(self):
        config = default_config()
        standard = resolve_workflow(config, {"profile": "standard"})
        self.assertTrue(standard["enabled"]["design"])
        self.assertFalse(standard["enabled"]["design_approval"])
        release = resolve_workflow(config, {"profile": "release"})
        self.assertEqual(release["target"], "deployed")
        self.assertTrue(release["enabled"]["design_approval"])
        invalid = [{"profile": "unknown"}, {"target": "local", "integration_position": "after_push", "stages": {"integration": True}},
                   {"stages": {"review": False}}, {"profile": "light", "stages": {"design_approval": True}},
                   {"stages": {"knowledge": "yes"}}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(HarnessError):
                validate_config({**config, "workflow": value})

    def test_cli_start_selects_a_real_light_route(self):
        self.flow.abort("Use the public CLI entry for this fixture")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--repo", str(self.root), "--task", "cli-task", "start", "--goal", "Small fix",
                         "--profile", "light", "--target", "local", "--enable", "knowledge"])
        result = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(result["active_stages"], ["intake", "plan", "implement", "review", "knowledge"])
        self.assertEqual(Workflow(self.root, "cli-task").load()["schema_version"], 3)

    def test_doctor_ignores_unselected_external_dependencies(self):
        path = self.root / ".harness/project.json"
        config = read_json(path)
        config["adapters"]["deploy"] = {"argv": ["missing-deployment-fixture"], "effect": "external"}
        atomic_json(path, config)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["--repo", str(self.root), "doctor", "--profile", "light", "--target", "local"]), 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "pass")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(["--repo", str(self.root), "doctor", "--profile", "release"])
        result = json.loads(out.getvalue())
        self.assertIn("adapters.push", result["missing_configuration"])
        self.assertIn("missing-deployment-fixture", result["missing_executables"][0])

    def test_completed_task_cannot_reactivate_over_another_active_task(self):
        self.light_review()
        Workflow(self.root, "second").start("Another task on the same branch", options={"profile": "light"})
        before = self.flow.path.read_bytes()
        with self.assertRaisesRegex(HarnessError, "active task"):
            self.flow.configure_flow({"target": "pr"}, "Extend old task")
        self.assertEqual(self.flow.path.read_bytes(), before)
        with self.assertRaisesRegex(HarnessError, "active task"):
            self.flow.reopen("review", "Recheck old task")

    def test_unsupported_state_is_rejected_without_modifying_it(self):
        state = self.flow.load()
        state["schema_version"] = 1
        atomic_json(self.flow.path, state)
        before = self.flow.path.read_bytes()
        with self.assertRaisesRegex(HarnessError, "Unsupported task schema_version"):
            self.flow.status()
        self.assertEqual(before, self.flow.path.read_bytes())

    def test_explicit_worktree_is_available_for_a_single_light_module(self):
        self.flow.configure_flow({"isolation": "worktree"}, "Keep this change isolated")
        self.light_intake()
        self.plan_tasks()
        self.flow.enter("implement")
        info = worktrees.prepare(self.flow, "core")
        self.assertNotEqual(Path(info["worktree"]), self.root)

    def test_checkout_test_failure_cannot_complete_the_module(self):
        self.light_intake()
        self.plan_tasks()
        self.flow.enter("implement")
        _, receipt = self.implement_module(fail=True)
        with self.assertRaises(HarnessError):
            self.verify_module("core", receipt)
        self.assertEqual(self.flow.status()["modules"]["core"]["status"], "running")
        self.write("feature_core.py", "def value():\n    return 2\n")
        self.commit("Repair observed checkout test failure")
        receipt = runner.run(self.flow, "check", "unit", module="core")
        self.verify_module("core", receipt)
        self.assertEqual(self.flow.status()["modules"]["core"]["status"], "merged")
