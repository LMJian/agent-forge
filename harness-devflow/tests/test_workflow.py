"""Behavioral tests with real repositories, commits, worktrees and subprocesses."""
from __future__ import annotations

import concurrent.futures
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from harness import gates, knowledge, runner, worktrees
from harness import git as vcs
from harness.cli import main
from harness.engine import Workflow, current, init_project
from harness.model import HarnessError, module_waves, validate_config
from harness.storage import atomic_json, read_json


class RepoCase(unittest.TestCase):
    def setUp(self):
        env_patch = patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
                                           "GIT_TERMINAL_PROMPT": "0", "PYTHONDONTWRITEBYTECODE": "1"})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.temp = tempfile.TemporaryDirectory(prefix="harness-flow-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.git("init", "-b", "main")
        self.git("config", "user.email", "fixture@example.test")
        self.git("config", "user.name", "Harness Fixture")
        self.git("config", "commit.gpgsign", "false")
        self.write(".gitignore", "__pycache__/\n*.pyc\n")
        self.write("base.py", "def value():\n    return 1\n")
        self.write("tests/test_base.py", "import unittest\nfrom base import value\n"
                   "class TestBase(unittest.TestCase):\n    def test_value(self):\n        self.assertEqual(value(), 1)\n")
        init_project(self.root, "main")
        self.configure()
        self.commit("Initial consumer")
        self.git("checkout", "-b", "feature/example")
        self.flow = Workflow(self.root, "example")
        self.flow.start("Add a reusable capability", "main")
        self.counter = 0

    def git(self, *args, root=None):
        return vcs.git(root or self.root, *args)

    def write(self, name, text, root=None):
        path = (root or self.root) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def configure(self, adapters=None):
        path = self.root / ".harness/project.json"
        config = read_json(path)
        config["checks"] = {"unit": {"argv": [sys.executable, "-m", "unittest", "discover", "-s", "tests"]}}
        config["stage_checks"] = {"review": ["unit"], "integration": ["unit"]}
        config["adapters"] = adapters or {}
        config["workflow"] = {"profile": "standard", "target": "local", "isolation": "worktree", "assistance": "autonomous",
                              "stages": {"design_approval": True, "interfaces": True}}
        atomic_json(path, config)

    def commit(self, message, root=None):
        self.git("add", ".", root=root)
        self.git("commit", "-m", message, root=root)

    def report(self, stage, **extra):
        self.counter += 1
        prefix = f".harness/runs/example/artifacts/{self.counter:03d}-{stage}"
        artifact = self.write(prefix + ".md", f"# {stage}\nEvidence for the reusable capability.\n")
        data = {"schema_version": 2, "stage": stage, "status": "pass", "summary": f"Completed {stage}",
                "artifacts": [str(artifact)], "findings": [], **extra}
        path = self.root / (prefix + "-report.json")
        atomic_json(path, data)
        return path

    def finish(self, stage, **extra):
        self.flow.enter(stage)
        path = self.report(stage, **extra)
        return self.flow.complete(stage, str(path))

    def to_approval(self, modules=None):
        modules = modules or [{"id": "core", "depends_on": [], "acceptance": ["AC-1"]}]
        self.finish("intake", details={"acceptance": ["AC-1"], "modules": modules})
        self.flow.enter("design")
        report = self.report("design")
        data = read_json(report)
        data["details"] = {"designs": {m["id"]: data["artifacts"][0] for m in modules}}
        atomic_json(report, data)
        self.flow.complete("design", str(report))
        self.finish("design_audit")
        self.finish("test_design", details={"scenarios": [{"id": "S-1", "acceptance": ["AC-1"]}]})
        self.flow.enter("design_approval")
        approval = self.report("design_approval")
        self.flow.complete("design_approval", str(approval), request_approval=True)
        return approval

    def to_implement(self, modules=None):
        self.to_approval(modules)
        self.flow.approve("design_approval", "fixture-user", "Approve these concrete design artifacts")
        self.flow.skip("interfaces", "No public schema or generated client changes")
        self.plan_tasks()
        self.flow.enter("implement")

    def plan_tasks(self):
        modules = self.flow.report_for(self.flow.load(), "intake")["details"]["modules"]
        path = self.root / ".harness/runs/example/artifacts/tasks.json"
        atomic_json(path, {m["id"]: [{"id": "build", "summary": "Implement the module's capability",
                                    "acceptance": m["acceptance"], "verification": "Run tests for the observable result"}]
                           for m in modules})
        result = self.flow.plan(str(path))
        if self.flow.load()["execution_mode"] == "worktree":
            from harness.branches import authorize
            for module in modules:
                authorize(self.flow, module=module["id"], actor="user",
                          note="Disposable test fixture user explicitly approves this module worktree")
        return result

    def implement_module(self, mid="core", fail=False):
        info = worktrees.prepare(self.flow, mid)
        wt = Path(info["worktree"])
        self.write(f"feature_{mid}.py", f"def value():\n    return {0 if fail else 2}\n", root=wt)
        self.write(f"tests/test_{mid}.py", f"import unittest\nfrom feature_{mid} import value\n"
                   "class TestFeature(unittest.TestCase):\n    def test_value(self):\n        self.assertEqual(value(), 2)\n", root=wt)
        self.commit(f"Implement {mid}", root=wt)
        receipt = runner.run(self.flow, "check", "unit", module=mid)
        return wt, receipt

    def verify_module(self, mid, receipt):
        path = self.report("implement")
        data = read_json(path)
        data.update(module=mid, completed_tasks=["build"],
                    acceptance=["AC-1"], checks=[receipt["id"]])
        atomic_json(path, data)
        return worktrees.complete(self.flow, mid, str(path))

    def to_review(self):
        self.to_implement()
        _, receipt = self.implement_module()
        self.assertEqual(receipt["status"], "passed", receipt)
        self.verify_module("core", receipt)
        worktrees.merge_wave(self.flow)
        self.finish("implement")
        self.flow.enter("review")

    def finish_review(self):
        self.to_review()
        receipt = runner.run(self.flow, "check", "unit")
        return self.flow.complete("review", str(self.report("review", checks=[receipt["id"]])))


class LifecycleTests(RepoCase):
    def test_local_workflow_reaches_completion_with_real_tests_and_approved_knowledge(self):
        self.flow.configure_flow({"stages": {"knowledge": True}, "knowledge_approval": True}, "Capture reviewed notes")
        self.finish_review()
        self.assertEqual(gates.gate(self.flow)["status"], "pass")
        self.flow.enter("integration")
        receipt = runner.run(self.flow, "check", "unit")
        self.flow.complete("integration", str(self.report("integration", checks=[receipt["id"]])))
        self.assertEqual(self.flow.status()["current_stage"], "knowledge")
        self.assertEqual(self.flow.status()["stages"]["release"], "skipped")
        self.flow.enter("knowledge")
        self.flow.complete("knowledge", str(self.report("knowledge", details={"outcome": "draft"})), request_approval=True)
        self.assertEqual(knowledge.search(self.root, "reusable")["results"], [])
        result = self.flow.approve("knowledge", "fixture-user", "Approve local reusable knowledge")
        self.assertEqual(result["status"], "complete")
        self.assertTrue(knowledge.search(self.root, "reusable")["results"])
        self.assertTrue(vcs.clean(self.root))

    def test_cannot_plan_or_create_worktrees_before_approval(self):
        self.to_approval()
        with self.assertRaises(HarnessError):
            self.plan_tasks()
        with self.assertRaises(HarnessError):
            worktrees.prepare(self.flow, "core")
        self.assertFalse((self.root / ".harness/worktrees").exists())

    def test_approval_requires_waiting_gate_and_nonempty_actor(self):
        with self.assertRaises(HarnessError):
            self.flow.approve("design_approval", "fixture-user", "Approve")
        self.to_approval()
        with self.assertRaises(HarnessError):
            self.flow.approve("design_approval", "", "Approve")
        with self.assertRaises(HarnessError):
            self.flow.complete("design_approval", str(self.report("design_approval")))

    def test_changed_design_blocks_approval_even_with_same_file_length(self):
        self.to_approval()
        state = self.flow.load()
        report = self.flow.report_for(state, "design")
        path = Path(report["artifacts"][0])
        path.write_text(path.read_text().replace("reusable", "modified"))
        with self.assertRaisesRegex(HarnessError, "stale"):
            self.flow.approve("design_approval", "fixture-user", "Approve")

    def test_unresolved_blocker_cannot_be_recorded_as_pass(self):
        self.to_approval()
        self.flow.reopen("design_audit", "Need another audit")
        self.flow.enter("design_audit")
        report = self.report("design_audit", findings=[{"severity": "blocker", "message": "Data loss"}])
        with self.assertRaisesRegex(HarnessError, "Unresolved blocker"):
            self.flow.complete("design_audit", str(report))

    def test_reopen_invalidates_downstream_and_preserves_history(self):
        self.to_implement()
        result = self.flow.reopen("design", "Requirements changed")
        self.assertEqual(result["current_stage"], "design")
        self.assertEqual(result["stages"]["design_approval"], "pending")
        self.assertEqual(result["waves"], [])
        self.assertTrue(self.flow.load()["history"])

    def test_missing_and_escaped_artifacts_cannot_complete(self):
        self.flow.enter("intake")
        outside = Path(self.temp.name).parent / "outside-harness-evidence.md"
        path = self.report("intake", artifacts=[str(outside)],
                           details={"acceptance": ["AC-1"], "modules": [{"id": "core", "acceptance": ["AC-1"]}]})
        with self.assertRaisesRegex(HarnessError, "escapes"):
            self.flow.complete("intake", str(path))

    def test_malicious_task_id_and_symlinked_run_directory_are_rejected(self):
        with self.assertRaises(HarnessError):
            Workflow(self.root, "../escape")
        (self.root / ".harness/runs/escape").symlink_to(self.root.parent, target_is_directory=True)
        with self.assertRaises(HarnessError):
            Workflow(self.root, "escape")

    def test_duplicate_task_on_branch_is_rejected(self):
        with self.assertRaisesRegex(HarnessError, "active task"):
            Workflow(self.root, "second").start("Second task")

    def test_wrong_checkout_does_not_mutate_state(self):
        old = self.flow.path.read_bytes()
        self.git("checkout", "main")
        with self.assertRaisesRegex(HarnessError, "owning checkout"):
            self.flow.enter("intake")
        self.assertEqual(old, self.flow.path.read_bytes())

    def test_concurrent_enter_is_idempotent_and_state_stays_valid(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.flow.enter("intake"), range(4)))
        self.assertTrue(all(r["status"] == "running" for r in results))
        state = read_json(self.flow.path)
        self.assertEqual(state["stages"]["intake"]["attempt"], 1)
        self.assertEqual(sum(e["action"] == "enter" for e in state["events"]), 1)

    def test_operational_config_change_does_not_require_design_reapproval(self):
        self.to_implement()
        path = self.root / ".harness/project.json"
        config = read_json(path)
        config["parallel_max"] = 2
        atomic_json(path, config)
        with self.assertRaisesRegex(HarnessError, "configuration changed"):
            self.flow.enter("implement")
        result = self.flow.sync_config("Use two module workers")
        self.assertEqual(result["current_stage"], "implement")
        self.assertEqual(result["stages"]["design_approval"], "done")

    def test_no_required_stage_can_be_skipped(self):
        with self.assertRaises(HarnessError):
            self.flow.skip("intake", "Convenience")

    def test_coverage_gaps_are_rejected(self):
        self.flow.enter("intake")
        report = self.report("intake", details={"acceptance": ["AC-1", "AC-2"],
                             "modules": [{"id": "core", "acceptance": ["AC-1"]}]})
        with self.assertRaisesRegex(HarnessError, "every acceptance"):
            self.flow.complete("intake", str(report))


class ExecutionTests(RepoCase):
    def test_downstream_worktree_contains_merged_upstream_modules(self):
        modules = [{"id": "core", "depends_on": [], "acceptance": ["AC-1"]},
                   {"id": "api", "depends_on": ["core"], "acceptance": ["AC-1"]}]
        self.to_implement(modules)
        with self.assertRaises(HarnessError):
            worktrees.prepare(self.flow, "api")
        _, receipt = self.implement_module("core")
        self.verify_module("core", receipt)
        worktrees.merge_wave(self.flow)
        info = worktrees.prepare(self.flow, "api")
        self.assertTrue((Path(info["worktree"]) / "feature_core.py").exists())
        self.assertEqual(info["base"], vcs.head(self.root))

    def test_failed_test_cannot_verify_module_and_fix_can_be_retested(self):
        self.to_implement()
        wt, failure = self.implement_module(fail=True)
        self.assertEqual(failure["status"], "failed")
        with self.assertRaises(HarnessError):
            self.verify_module("core", failure)
        self.write("feature_core.py", "def value():\n    return 2\n", root=wt)
        self.commit("Fix observed result", root=wt)
        passed = runner.run(self.flow, "check", "unit", module="core")
        self.assertEqual(passed["status"], "passed", passed)
        self.verify_module("core", passed)

    def test_worktree_changed_after_verification_prevents_merge(self):
        self.to_implement()
        wt, receipt = self.implement_module()
        self.verify_module("core", receipt)
        self.write("feature_core.py", "def value():\n    return 3\n", root=wt)
        self.commit("Change after checks", root=wt)
        with self.assertRaisesRegex(HarnessError, "changed after verification"):
            worktrees.merge_wave(self.flow)

    def test_check_receipt_from_different_stage_is_not_accepted(self):
        self.to_review()
        old = next(r for r in self.flow.load()["runs"] if r["stage"] == "implement")
        with self.assertRaises(HarnessError):
            self.flow.complete("review", str(self.report("review", checks=[old["id"]])))

    def test_new_commit_invalidates_review_and_push(self):
        self.finish_review()
        self.write("new.py", "new_value = 1\n")
        self.commit("Post-review change")
        self.assertEqual(self.flow.status()["status"], "stale")
        with self.assertRaises(HarnessError):
            gates.gate(self.flow)

    def test_missing_check_receipt_never_passes(self):
        self.to_review()
        with self.assertRaises(HarnessError):
            self.flow.complete("review", str(self.report("review", checks=["invented"])) )

    def test_expired_review_blocks_push(self):
        self.finish_review()
        state = self.flow.load()
        state["stages"]["review"]["ended_at"] = "2000-01-01T00:00:00+00:00"
        atomic_json(self.flow.path, state)
        with self.assertRaisesRegex(HarnessError, "Review expired"):
            gates.gate(self.flow)

    def test_cli_fails_with_structured_error_instead_of_traceback(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = main(["--repo", str(self.root), "--task", "example", "run-check", "unit"])
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(err.getvalue())["status"], "blocked")

    def test_git_hook_preserves_existing_hook(self):
        hook = self.root / ".git/hooks/pre-push"
        hook.write_text("#!/bin/sh\necho existing\n")
        with self.assertRaisesRegex(HarnessError, "existing pre-push"):
            gates.install(self.root, Path(__file__).resolve().parent.parent)
        self.assertIn("echo existing", hook.read_text())

    def test_git_hook_blocks_real_unreviewed_push(self):
        remote = self.root / ".harness/runs/remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
        self.git("remote", "add", "test", str(remote))
        gates.install(self.root, Path(__file__).resolve().parent.parent)
        result = subprocess.run(["git", "-C", str(self.root), "push", "test", "HEAD:refs/heads/example"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("review", result.stderr.lower())

    def test_partial_merge_conflict_can_resume_without_losing_completed_modules(self):
        modules = [{"id": "one", "acceptance": ["AC-1"]}, {"id": "two", "acceptance": ["AC-1"]}]
        self.to_implement(modules)
        for mid in ("one", "two"):
            wt, receipt = self.implement_module(mid)
            self.write("shared.txt", mid + "\n", root=wt)
            self.commit("Add shared module configuration", root=wt)
            receipt = runner.run(self.flow, "check", "unit", module=mid)
            self.verify_module(mid, receipt)
        with self.assertRaises(HarnessError):
            worktrees.merge_wave(self.flow)
        self.assertEqual(self.flow.load()["modules"]["one"]["status"], "merged")
        self.write("shared.txt", "one\ntwo\n")
        self.git("add", "shared.txt")
        self.git("commit", "--no-edit")
        result = worktrees.merge_wave(self.flow)
        self.assertEqual(result["wave_index"], 1)
        self.assertEqual((self.root / "shared.txt").read_text(), "one\ntwo\n")

    def test_prepare_recovers_existing_worktree_after_interrupted_state_write(self):
        self.to_implement()
        epoch = self.flow.load()["stages"]["implement"]["epoch"]
        path = self.root / f".harness/worktrees/example/{epoch}/core"
        path.parent.mkdir(parents=True)
        self.git("worktree", "add", "-b", f"harness/example/{epoch}/core", str(path), "HEAD")
        result = worktrees.prepare(self.flow, "core")
        self.assertEqual(result["worktree"], str(path))

    def test_interrupted_run_can_only_be_abandoned_after_processes_exit(self):
        self.flow.enter("intake")
        state = self.flow.load()
        # Simulate durable receipt left by a process that has exited.
        process = subprocess.Popen([sys.executable, "-c", "pass"])
        process.wait()
        state["runs"].append({"id": "interrupted", "status": "running", "owner_pid": os.getpid(),
                              "child_pid": process.pid})
        atomic_json(self.flow.path, state)
        with self.assertRaisesRegex(HarnessError, "still alive"):
            runner.reconcile(self.flow, "interrupted", "Inspected logs")
        state["runs"][0]["owner_pid"] = process.pid
        atomic_json(self.flow.path, state)
        result = runner.reconcile(self.flow, "interrupted", "Confirmed both processes exited and no external effects")
        self.assertEqual(result["status"], "failed")


class ContractTests(unittest.TestCase):
    def test_unknown_dependencies_self_dependencies_cycles_and_duplicates_rejected(self):
        invalid = [
            [{"id": "one", "depends_on": ["missing"]}],
            [{"id": "one", "depends_on": ["one"]}],
            [{"id": "one", "depends_on": ["two"]}, {"id": "two", "depends_on": ["one"]}],
            [{"id": "one"}, {"id": "one"}],
        ]
        for modules in invalid:
            with self.subTest(modules=modules), self.assertRaises(HarnessError):
                module_waves(modules)

    def test_graph_preserves_independent_modules_and_dependency_order(self):
        modules = [{"id": "a"}, {"id": "b"}, {"id": "c", "depends_on": ["a", "b"]}]
        self.assertEqual(module_waves(modules), [["a", "b"], ["c"]])

    def test_shell_string_configuration_is_rejected(self):
        with self.assertRaises(HarnessError):
            validate_config({"schema_version": 2, "checks": {"unit": {"argv": "echo pass; true"}}})

    def test_adapter_result_is_strict(self):
        with self.assertRaises(HarnessError):
            runner.validate_response({"status": "pass"}, "pr")
        with self.assertRaises(HarnessError):
            runner.validate_response({"schema_version": 1, "status": "pass", "summary": "PR exists"}, "pr")


if __name__ == "__main__":
    unittest.main()
