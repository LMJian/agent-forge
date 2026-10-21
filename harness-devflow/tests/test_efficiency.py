"""Existing-change delivery, conservative receipt reuse and scoped context with real Git."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

from harness import gates, guidance, runner
from harness import git as vcs
from harness.context import acknowledge, references
from harness.engine import Workflow
from harness.model import HarnessError
from harness.reuse import reuse
from harness.storage import atomic_json, read_json
import test_host_execution as support
from test_workflow import RepoCase


class ExistingChangesTests(RepoCase):
    cli = support.PortableExecutionTests.cli
    body = support.PortableExecutionTests.body

    def setUp(self):
        super().setUp()
        self.flow.abort("Switch fixture to reviewing existing changes")
        config = read_json(self.root / ".harness/project.json")
        config["stage_checks"]["integration"] = []
        config["workflow"] = {}
        config["checks"]["unit"]["reuse"] = {
            "context_files": [".local-toolchain"], "max_age_seconds": 7200,
            "assumptions": "Offline stdlib-only tests; independent of Git history and HARNESS variables"}
        atomic_json(self.root / ".harness/project.json", config)
        self.write(".gitignore", "__pycache__/\n*.pyc\n.local-toolchain\n")
        self.write(".local-toolchain", "fixture-runtime-1")
        self.commit("Configure deterministic local review")
        self.flow = Workflow(self.root, "existing")

    def start_review(self, target="local"):
        return self.cli("start-review", "--goal", "Review existing value behavior", "--base", "main",
                        "--acceptance", "base.value remains 1", "--target", target)

    def check(self):
        self.cli("next")
        return self.cli("run-check", "unit")

    def finish_review(self):
        return self.cli("submit", "--result", str(self.body("review")))

    def test_existing_dirty_diff_starts_directly_at_review_without_fake_history(self):
        self.write("note.txt", "An existing uncommitted change\n")
        result = self.start_review()
        self.assertEqual(result["active_stages"], ["review"])
        packet = self.cli("next")
        self.assertEqual(packet["review_context"]["acceptance"], ["base.value remains 1"])
        self.assertTrue(packet["initial_dirty"])
        self.assertEqual(self.check()["status"], "passed")
        self.assertEqual(self.finish_review()["status"], "complete")
        state = self.flow.load()
        self.assertFalse(state["modules"])
        self.assertNotIn("report", state["stages"]["implement"])

    def test_push_only_uses_real_bare_remote_and_verifies_exact_head(self):
        remote = self.root.parent / (self.root.name + "-remote.git")
        import shutil
        self.addCleanup(shutil.rmtree, remote, True)
        self.git("init", "--bare", str(remote))
        self.git("remote", "add", "fixture", str(remote))
        config = read_json(self.root / ".harness/project.json")
        config["adapters"]["push"] = {"argv": [sys.executable, "{plugin_root}/adapters/git_push.py", "--remote", "fixture"],
                                        "effect": "external"}
        atomic_json(self.root / ".harness/project.json", config)
        self.commit("Configure explicit local bare remote")
        self.start_review("pushed")
        self.check()
        self.assertEqual(self.finish_review()["current_stage"], "push")
        self.cli("next")
        denied = self.cli("run-adapter", "push", expected=2)
        self.assertIn("authorization", str(denied))
        receipt = self.cli("run-adapter", "push", "--authorization", "Push this fixture to its temporary bare remote")
        self.assertEqual(receipt["status"], "passed", receipt)
        self.assertEqual(receipt["response"]["remote_head"], vcs.head(self.root))
        self.assertEqual(self.cli("submit", "--result", str(self.body("push")))["status"], "complete")
        self.assertEqual(self.git("ls-remote", "fixture", "refs/heads/feature/example").split()[0], vcs.head(self.root))
        self.assertFalse(self.flow.load()["workflow"]["enabled"]["pr"])

    def test_commit_identical_tested_bytes_reuses_check_but_requires_new_review(self):
        self.write("note.txt", "Already tested bytes\n")
        self.start_review("pushed")
        receipt = self.check()
        self.finish_review()
        self.commit("Commit the exact reviewed bytes")
        with self.assertRaises(HarnessError):
            gates.gate(self.flow)
        self.flow.reopen("review", "Reassess the final commit with unchanged deterministic test inputs")
        self.cli("next")
        copied = self.cli("reuse-check", "unit", "--from", receipt["id"])
        self.assertEqual(copied["reused_from"], receipt["id"])
        self.assertEqual(copied["finished_at"], receipt["finished_at"])
        self.finish_review()
        self.assertEqual(gates.gate(self.flow)["head"], vcs.head(self.root))
        with self.assertRaisesRegex(HarnessError, "running local .*stage"):
            reuse(self.flow, "unit", receipt["id"])

    def test_changed_code_ignored_inputs_environment_and_logs_each_reject_reuse(self):
        self.start_review()
        receipt = self.check()
        self.write("extra.txt", "new input")
        with self.assertRaisesRegex(HarnessError, "inputs"):
            reuse(self.flow, "unit", receipt["id"])
        (self.root / "extra.txt").unlink()
        self.write(".local-toolchain", "fixture-runtime-2")
        with self.assertRaisesRegex(HarnessError, "inputs"):
            reuse(self.flow, "unit", receipt["id"])
        self.write(".local-toolchain", "fixture-runtime-1")
        with patch.dict(os.environ, {"HARNESS_FIXTURE_NONDETERMINISM": "excluded", "TEST_MODE": "changed"}):
            with self.assertRaisesRegex(HarnessError, "environment"):
                reuse(self.flow, "unit", receipt["id"])
        Path(receipt["stderr"]).write_text("tampered check log")
        with self.assertRaisesRegex(HarnessError, "Artifact changed"):
            reuse(self.flow, "unit", receipt["id"])

    def test_reuse_does_not_renew_expiry_or_hide_changed_inputs_at_delivery(self):
        from datetime import datetime, timedelta, timezone
        self.start_review("pushed")
        receipt = self.check()
        with patch("harness.reuse.datetime") as clock:
            clock.now.return_value = datetime.now(timezone.utc) + timedelta(days=2)
            clock.fromisoformat.side_effect = datetime.fromisoformat
            with self.assertRaisesRegex(HarnessError, "expired"):
                reuse(self.flow, "unit", receipt["id"])
        reuse(self.flow, "unit", receipt["id"])
        self.finish_review()
        self.write(".local-toolchain", "changed after review")
        with self.assertRaisesRegex(HarnessError, "inputs"):
            gates.gate(self.flow)

    def test_a_later_failed_check_prevents_reusing_an_older_pass(self):
        self.start_review()
        passed = self.check()
        self.write("base.py", "def value():\n    return 2\n")
        self.assertEqual(runner.run(self.flow, "check", "unit")["status"], "failed")
        self.write("base.py", "def value():\n    return 1\n")
        with self.assertRaisesRegex(HarnessError, "newer failed"):
            reuse(self.flow, "unit", passed["id"])
        with self.assertRaisesRegex(HarnessError, "newer failed"):
            self.flow.complete("review", str(self.report("review", checks=[passed["id"]])))

    def test_submission_selects_the_latest_check_for_each_command(self):
        self.start_review()
        self.check()
        newest = self.check()
        self.finish_review()
        report = self.flow.report_for(self.flow.load(), "review")
        self.assertEqual(report["checks"], [newest["id"]])

    def test_content_identity_tracks_modes_and_preserves_unusual_filenames(self):
        self.write(" leading name.txt", "same bytes\n")
        before = vcs.content_fingerprint(self.root)
        self.commit("Commit existing input bytes")
        self.assertEqual(vcs.content_fingerprint(self.root), before)
        file = self.root / " leading name.txt"
        file.chmod(file.stat().st_mode | 0o111)
        self.assertNotEqual(vcs.content_fingerprint(self.root), before)


class ScopedContextTests(RepoCase):
    def test_stage_context_filters_history_and_reports_read_freshness(self):
        self.to_approval()
        self.flow.approve("design_approval", "fixture", "Approve fixture")
        self.flow.skip("interfaces", "No interface changes")
        self.plan_tasks()
        self.flow.enter("implement")
        packet = guidance.packet(self.flow, self.flow.load())
        self.assertNotIn("design_audit", {r["stage"] for r in packet["inputs"]})
        self.assertIn("design_audit", {r["stage"] for r in references(self.flow, self.flow.load(), all_inputs=True)})
        design = next(r for r in packet["inputs"] if r["stage"] == "design")
        self.assertEqual(design["read_status"], "unread")
        acknowledge(self.flow, design["content_id"])
        again = guidance.packet(self.flow, self.flow.load())
        self.assertEqual(next(r for r in again["inputs"] if r["stage"] == "design")["read_status"], "unchanged")
        with self.assertRaisesRegex(HarnessError, "Unknown or changed"):
            acknowledge(self.flow, "not-a-current-content-id")
        self.flow.reopen("design", "Update design after a new finding")
        self.flow.enter("design")
        report = self.report("design")
        body = read_json(report)
        body["details"] = {"designs": {"core": body["artifacts"][0]}}
        atomic_json(report, body)
        self.flow.complete("design", str(report))
        changed = references(self.flow, self.flow.load())
        self.assertEqual(next(r for r in changed if r["stage"] == "design")["read_status"], "changed")
