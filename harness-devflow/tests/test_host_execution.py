"""Real command/worktree paths and guided fallback behavior, independent of installed AI hosts."""
import contextlib
import io
import json
from pathlib import Path
import sys

from harness import guidance, hosts, runner, worktrees, gates
from harness import git as vcs
from harness.cli import main, parser
from harness.engine import Workflow
from harness.model import HarnessError, default_config, validate_config
from harness.storage import atomic_json, read_json
from test_workflow import RepoCase


BRIDGE = '''import json, os, subprocess
from pathlib import Path
req = json.loads(Path(os.environ["HARNESS_HOST_REQUEST"]).read_text())
p = subprocess.run(req["argv"], cwd=req["cwd"], env={**os.environ, **req["environment"]}, capture_output=True, text=True, timeout=req["timeout_seconds"])
print(json.dumps({"schema_version": 1, "request_id": req["request_id"], "outcome": "completed", "exit_code": p.returncode, "timed_out": False, "stdout": p.stdout, "stderr": p.stderr}))
'''


class PortableExecutionTests(RepoCase):
    def setUp(self):
        super().setUp()
        self.flow.configure_flow({"profile": "light", "assistance": "guided", "isolation": "checkout",
                                  "stages": {"design_approval": False, "interfaces": False, "integration": False}},
                                 "A guided local implementation fixture")

    def cli(self, *args, expected=0):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--repo", str(self.root), "--task", self.flow.task, *args])
        self.assertEqual(code, expected, err.getvalue() or out.getvalue())
        return json.loads((out if code in {0, 1} else err).getvalue())

    def body(self, stage, **fields):
        path = self.report(stage, **fields)
        value = read_json(path)
        value.pop("stage")
        value.pop("schema_version")
        atomic_json(path, value)
        return path

    def intake(self):
        self.cli("next")
        body = self.body("intake", details={"acceptance": ["AC-1"], "modules": [{"id": "core", "acceptance": ["AC-1"]}],
                                           "approach": "Extend the value behavior", "verification": "Assert the exported value"})
        self.cli("submit", "--result", str(body))

    def ready(self):
        self.intake()
        self.plan_tasks()
        return self.cli("next")

    def host(self, *, bridge=None, available=None, worktree="auto"):
        cfg = read_json(self.root / ".harness/project.json")
        cfg["host"] = {"name": "test-host", "available": available or [], "worktree": worktree,
                       "command": {"provider": "auto"}}
        if bridge is not None:
            self.write(".harness/test-bridge.py", bridge)
            cfg["host"]["command"]["bridge"] = {"argv": [sys.executable, str(self.root / ".harness/test-bridge.py")]}
        atomic_json(self.root / ".harness/project.json", cfg)
        self.commit("Configure explicit host fixture")
        self.flow.sync_config("Use the test host capabilities")

    def checkpoint(self, receipt, step="build", expected=0):
        artifact = self.write(f".harness/runs/{self.flow.task}/artifacts/{step}-observed.md",
                              "The feature returns 2; the configured unit suite passed.\n")
        return self.cli("checkpoint", "--module", "core", "--step", step,
                        "--summary", "Implemented and checked the value", "--check", receipt["id"], "--artifact", str(artifact), expected=expected)

    def test_public_guided_cli_completes_with_dirty_code_and_no_native_capabilities(self):
        self.flow.abort("Start with existing user work")
        self.write("user-notes.txt", "preserve existing user work\n")
        self.flow = Workflow(self.root, "dirty")
        self.flow.start("Implement without committing user changes", options={"profile": "light", "assistance": "guided", "isolation": "checkout",
                        "stages": {"design_approval": False, "interfaces": False, "integration": False}})
        self.assertTrue(self.flow.load()["initial_dirty"])
        packet = self.ready()
        self.assertEqual(packet["action"]["kind"], "prepare_module")
        self.assertEqual(packet["execution"]["command"], "builtin")
        self.assertEqual(packet["execution"]["delegation"], "serial")
        self.cli("prepare-module", "core")
        self.write("feature_core.py", "def value():\n    return 2\n")
        self.write("tests/test_core.py", "import unittest\nfrom feature_core import value\nclass Feature(unittest.TestCase):\n def test_value(self): self.assertEqual(value(), 2)\n")
        receipt = self.cli("run-check", "unit", "--module", "core")
        body = self.body("implement", completed_tasks=["build"], acceptance=["AC-1"], checks=[receipt["id"]])
        self.cli("submit-module", "core", "--result", str(body), expected=2)
        self.checkpoint(receipt)
        self.assertEqual(self.cli("next")["action"]["kind"], "submit_module")
        self.cli("submit-module", "core", "--result", str(body))
        self.cli("submit", "--result", str(self.body("implement")))
        self.cli("next")
        self.cli("run-check", "unit")
        result = self.cli("submit", "--result", str(self.body("review")))
        self.assertEqual(result["status"], "complete")
        self.assertFalse(vcs.clean(self.root))
        self.assertEqual((self.root / "user-notes.txt").read_text(), "preserve existing user work\n")
        with self.assertRaises(HarnessError):
            gates.gate(self.flow)

    def test_guided_packet_exposes_only_next_task_and_enforces_order(self):
        self.intake()
        tasks = {"core": [{"id": name, "summary": "Implement " + name, "acceptance": ["AC-1"], "verification": "Run unit"}
                          for name in ("first", "second")]}
        path = self.root / ".harness/runs/example/artifacts/tasks.json"
        atomic_json(path, tasks)
        self.flow.plan(str(path))
        self.cli("next")
        _, receipt = self.implement_module()
        self.assertEqual([t["id"] for t in self.cli("next")["tasks"]], ["first"])
        with self.assertRaisesRegex(HarnessError, "next planned"):
            worktrees.checkpoint(self.flow, "core", "second", "Out of order", [receipt["id"]], [str(path)])
        self.checkpoint(receipt, "first")
        self.assertEqual([t["id"] for t in self.cli("next")["tasks"]], ["second"])

    def test_failed_or_stale_checks_cannot_satisfy_guided_checkpoint(self):
        self.ready()
        _, failed = self.implement_module(fail=True)
        artifact = self.write(".harness/runs/example/artifacts/observed.md", "Observed failure\n")
        with self.assertRaisesRegex(HarnessError, "current passed"):
            worktrees.checkpoint(self.flow, "core", "build", "Attempt", [failed["id"]], [str(artifact)])
        self.write("feature_core.py", "def value():\n    return 2\n")
        passed = runner.run(self.flow, "check", "unit", module="core")
        self.write("feature_core.py", "def value():\n    return 3\n")
        with self.assertRaisesRegex(HarnessError, "current passed"):
            worktrees.checkpoint(self.flow, "core", "build", "Attempt", [passed["id"]], [str(artifact)])

    def test_missing_host_capabilities_use_serial_builtin_worktrees(self):
        self.flow.configure_flow({"isolation": "worktree", "assistance": "autonomous"}, "Exercise builtin fallback")
        self.cli("next")
        body = self.body("intake", details={"acceptance": ["AC-1"], "approach": "Two modules", "verification": "Unit suite",
                                           "modules": [{"id": "core", "acceptance": ["AC-1"]}, {"id": "api", "acceptance": ["AC-1"]}]})
        self.cli("submit", "--result", str(body))
        self.plan_tasks()
        self.cli("next")
        _, receipt = self.implement_module("core")
        with self.assertRaisesRegex(HarnessError, "Serial execution"):
            worktrees.prepare(self.flow, "api")
        self.verify_module("core", receipt)
        _, receipt = self.implement_module("api")
        self.verify_module("api", receipt)
        worktrees.merge_wave(self.flow)
        self.finish("implement")
        self.flow.enter("review")
        receipt = runner.run(self.flow, "check", "unit")
        self.assertEqual(self.flow.complete("review", str(self.report("review", checks=[receipt["id"]])))["status"], "complete")

    def test_native_command_executes_actual_checks_with_same_receipt_contract(self):
        self.host(bridge=BRIDGE)
        self.ready()
        _, receipt = self.implement_module()
        self.assertEqual(receipt["provider"], "native")
        self.assertEqual(receipt["status"], "passed", receipt)
        self.assertIn("Ran 2 tests", Path(receipt["stderr"]).read_text())
        self.assertTrue(any(e["path"].endswith("host-request.json") for e in receipt["evidence"]))
        self.checkpoint(receipt)
        self.verify_module("core", receipt)
        self.finish("implement")
        self.flow.enter("review")
        receipt = runner.run(self.flow, "check", "unit")
        self.assertEqual(self.flow.complete("review", str(self.report("review", checks=[receipt["id"]])))["status"], "complete")

    def test_native_failed_command_is_not_retried_through_builtin(self):
        self.host(bridge=BRIDGE)
        self.ready()
        _, receipt = self.implement_module(fail=True)
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["provider"], "native")
        self.assertEqual(len(self.flow.load()["runs"]), 1)
        self.checkpoint(receipt, expected=2)

    def test_native_denial_or_bad_request_binding_blocks_retry_and_provider_changes(self):
        self.host(bridge='import json,os\nfrom pathlib import Path\nr=json.loads(Path(os.environ["HARNESS_HOST_REQUEST"]).read_text())\nprint(json.dumps({"schema_version":1,"request_id":r["request_id"],"outcome":"denied"}))\n')
        self.ready()
        _, receipt = self.implement_module()
        self.assertEqual(receipt["status"], "unresolved")
        self.assertEqual(self.cli("next")["action"]["kind"], "inspect_execution")
        with self.assertRaisesRegex(HarnessError, "unresolved"):
            runner.run(self.flow, "check", "unit", module="core")
        with self.assertRaises(HarnessError):
            self.flow.configure_flow({"target": "pr"}, "Cannot hide unresolved execution")
        self.assertEqual(runner.reconcile(self.flow, receipt["id"], "Host confirmed the command was denied and never ran")["status"], "failed")

    def test_native_bridge_wrong_request_id_is_not_trusted(self):
        self.host(bridge='print(\'{"schema_version":1,"request_id":"wrong","outcome":"completed","exit_code":0,"timed_out":false,"stdout":"","stderr":""}\')\n')
        self.ready()
        _, receipt = self.implement_module()
        self.assertEqual(receipt["status"], "unresolved")
        self.assertIn("does not match", receipt["error"])

    def test_tampered_native_command_log_is_rejected(self):
        self.host(bridge=BRIDGE)
        self.ready()
        _, receipt = self.implement_module()
        Path(receipt["stderr"]).write_text("fabricated pass\n")
        self.checkpoint(receipt, expected=2)

    def test_native_detached_worktree_is_attached_verified_and_merged(self):
        self.host(available=["worktree"])
        self.flow.configure_flow({"isolation": "worktree"}, "Use host isolation")
        self.ready()
        request = worktrees.prepare(self.flow, "core")
        self.assertEqual(request["status"], "awaiting_host")
        host_path = self.root.parent / (self.root.name + "-host")
        self.addCleanup(lambda: self.git("worktree", "remove", "--force", str(host_path)) if host_path.exists() else None)
        self.git("worktree", "add", "--detach", str(host_path), request["base"])
        attached = self.cli("attach-worktree", "core", "--path", str(host_path))
        self.assertIsNone(attached["branch"])
        _, receipt = self.implement_module()
        self.checkpoint(receipt)
        self.verify_module("core", receipt)
        worktrees.merge_wave(self.flow)
        self.assertTrue((self.root / "feature_core.py").is_file())
        self.assertTrue(host_path.exists())

    def test_native_worktree_rejects_wrong_base_or_unrelated_repo(self):
        self.host(available=["worktree"])
        self.flow.configure_flow({"isolation": "worktree"}, "Use host isolation")
        self.ready()
        worktrees.prepare(self.flow, "core")
        path = self.root / ".harness/wrong-base"
        self.git("worktree", "add", "--detach", str(path), "HEAD~1")
        with self.assertRaisesRegex(HarnessError, "base SHA"):
            worktrees.attach(self.flow, "core", str(path))
        unrelated = self.root / ".harness/unrelated"
        unrelated.mkdir()
        self.git("init", "-b", "main", root=unrelated)
        with self.assertRaisesRegex(HarnessError, "repository mismatch"):
            worktrees.attach(self.flow, "core", str(unrelated))

    def test_detached_owning_checkout_can_finish_and_bind_a_named_branch(self):
        self.flow.abort("Use a detached checkout")
        self.git("checkout", "--detach")
        self.flow = Workflow(self.root, "detached")
        self.flow.start("Local detached feature", options={"profile": "light", "assistance": "guided", "isolation": "checkout",
                        "stages": {"design_approval": False, "interfaces": False, "integration": False}})
        self.ready()
        _, receipt = self.implement_module()
        self.checkpoint(receipt)
        self.verify_module("core", receipt)
        self.finish("implement")
        self.flow.enter("review")
        receipt = runner.run(self.flow, "check", "unit")
        self.flow.complete("review", str(self.report("review", checks=[receipt["id"]])))
        self.git("switch", "-c", "host-created-branch")
        result = self.cli("bind-branch", "--reason", "Name the verified detached work for delivery")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(gates.gate(self.flow)["status"], "pass")

    def test_assistance_cannot_be_weakened_after_plan(self):
        self.ready()
        with self.assertRaisesRegex(HarnessError, "checkpoints"):
            self.flow.configure_flow({"assistance": "autonomous"}, "Skip the remaining checkpoints")

    def test_handoff_reconstructs_next_task_in_a_fresh_runtime_instance(self):
        self.ready()
        worktrees.prepare(self.flow, "core")
        output = self.root / ".harness/runs/example/artifacts/handoff.json"
        self.cli("handoff", "--output", str(output))
        fresh = Workflow(self.root, "example")
        packet = guidance.advance(fresh)
        self.assertEqual(read_json(output)["goal"], packet["goal"])
        self.assertEqual(packet["tasks"][0]["id"], "build")
        self.assertTrue(packet["inputs"])

    def test_command_log_changes_after_review_invalidate_delivery_gate(self):
        self.ready()
        _, receipt = self.implement_module()
        self.checkpoint(receipt)
        self.verify_module("core", receipt)
        self.finish("implement")
        self.flow.enter("review")
        receipt = runner.run(self.flow, "check", "unit")
        self.flow.complete("review", str(self.report("review", checks=[receipt["id"]])))
        Path(receipt["stderr"]).write_text("Altered historical test output\n")
        self.assertEqual(self.flow.status()["status"], "stale")
        with self.assertRaises(HarnessError):
            gates.gate(self.flow)

    def test_doctor_validates_native_bridge_executable(self):
        cfg = read_json(self.root / ".harness/project.json")
        cfg["host"] = {"command": {"provider": "native", "bridge": {"argv": ["missing-test-host-bridge"]}}}
        atomic_json(self.root / ".harness/project.json", cfg)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--repo", str(self.root), "doctor", "--profile", "light", "--disable", "interfaces", "--disable", "design_approval"])
        self.assertEqual(code, 1)
        self.assertIn("host.command.bridge", json.loads(out.getvalue())["missing_executables"][0])

    def test_batch_stops_for_required_approval_and_preserves_remaining_work(self):
        self.flow.configure_flow({"profile": "standard", "assistance": "autonomous", "stages": {"design_approval": True}}, "Review design")
        intake = self.body("intake", details={"acceptance": ["AC-1"], "modules": [{"id": "core", "acceptance": ["AC-1"]}]})
        design = self.body("design")
        value = read_json(design)
        value["details"] = {"designs": {"core": value["artifacts"][0]}}
        atomic_json(design, value)
        audit = self.body("design_audit")
        scenarios = self.body("test_design", details={"scenarios": [{"id": "S-1", "acceptance": ["AC-1"]}]})
        approval = self.body("design_approval")
        remaining = self.body("interfaces")
        batch = self.root / ".harness/runs/example/artifacts/batch.json"
        atomic_json(batch, {"results": [str(p) for p in (intake, design, audit, scenarios, approval, remaining)]})
        result = self.cli("submit-batch", "--results", str(batch))
        self.assertEqual(result["status"], "waiting_human")
        self.assertEqual(result["submitted"], 5)
        self.assertEqual(result["remaining"], [str(remaining)])
        self.assertEqual(self.flow.status()["stages"]["design_approval"], "waiting_human")

    def test_autonomous_batch_preserves_successful_prefix_on_invalid_result(self):
        self.flow.configure_flow({"assistance": "autonomous"}, "Batch fixture")
        intake = self.body("intake", details={"acceptance": ["AC-1"], "modules": [{"id": "core", "acceptance": ["AC-1"]}],
                                             "approach": "Small change", "verification": "Unit"})
        invalid = self.body("plan", details={"waves": [["wrong"]], "tasks": {}})
        batch = self.root / ".harness/runs/example/artifacts/batch.json"
        atomic_json(batch, {"results": [str(intake), str(invalid)]})
        self.cli("submit-batch", "--results", str(batch), expected=2)
        self.assertEqual(self.flow.status()["stages"]["intake"], "done")
        self.assertEqual(self.flow.status()["current_stage"], "plan")

    def test_unsupported_state_and_config_are_rejected_without_writes(self):
        original = self.flow.load()
        for version in (1, 2):
            atomic_json(self.flow.path, {**original, "schema_version": version})
            before = self.flow.path.read_bytes()
            with self.assertRaisesRegex(HarnessError, "Unsupported task"):
                self.flow.status()
            self.assertEqual(before, self.flow.path.read_bytes())
        with self.assertRaisesRegex(HarnessError, "Unsupported project"):
            validate_config({"schema_version": 1})


class HostSelectionTests(RepoCase):
    def test_vendor_name_does_not_imply_capabilities_or_weaken_guidance(self):
        for name in ("generic", "codex", "claude-code", "custom-agent"):
            selected = hosts.resolve({"name": name}, "guided")
            self.assertEqual(selected["command"], "builtin")
            self.assertEqual(selected["worktree"], "builtin")
            self.assertEqual(selected["delegation"], "serial")
        self.assertEqual(default_config()["workflow"]["assistance"], "autonomous")

    def test_explicit_native_requires_actual_integration(self):
        for config in ({"command": {"provider": "native"}}, {"worktree": "native"}):
            with self.assertRaises(HarnessError):
                hosts.validate(config)

    def test_removed_cli_entrypoints_have_no_aliases(self):
        for name in ("enter", "complete", "request-approval", "resume", "prepare-capability", "complete-capability", "complete-module", "abandon-run"):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parser().parse_args([name])
