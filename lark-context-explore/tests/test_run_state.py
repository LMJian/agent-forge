"""Offline ledger regressions. CLI responses and parser modules are synthetic fixtures."""
import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import check_artifacts as checks
import run_state as state
from record_validation import assess, check_files, context_key, coverage, digest, local_path


class LedgerFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run, self.evidence = checks.initial_state("Fixture", read_only=True)
        self.run["questions"] = [{"id": "q1", "text": "What is the design?", "requires": ["document"],
                                  "status": "unanswered", "claim_ids": [], "gaps": ["not read yet"]}]
        state.clock(self.run, "start", "collection")
        self.request = {"argv": ["lark-cli", "docs", "+fetch", "--doc", "fixture-token", "--scope", "outline", "--as", "user"],
                        "phase": "collection", "execution_context": {"runner": "native-shell", "sandbox": "default", "identity": "user"},
                        "question_ids": ["q1"]}

    def save(self):
        state.save(self.root / "run.json", self.run)
        state.save(self.root / "evidence.json", self.evidence)

    def invoke(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / "run_state.py"), args[0], str(self.root), *args[1:]],
                              capture_output=True, text=True)

    def complete(self, reservation, response=None, err="", code=0):
        response = response if response is not None else {"ok": True, "identity": "user", "data": {"document": {"revision_id": 7, "content": "fixture design"}}}
        (self.root / reservation["capture_stdout"]).write_text(json.dumps(response))
        (self.root / reservation["capture_stderr"]).write_text(err)
        return state.finish(self.root, self.run, reservation["call_id"], reservation["capture_stdout"], reservation["capture_stderr"], code)

    def probe(self):
        reservation = state.prepare(self.root, self.run, self.request, probe=True)
        self.complete(reservation)
        return reservation

    def fact(self):
        reservation = self.probe()
        self.save()
        state.source(self.root, self.run, argparse.Namespace(call_id=reservation["call_id"], id="s1", kind="document",
                     locator="https://example.invalid/doc#design", scope="outline", provenance="primary"))
        self.evidence = json.loads((self.root / "evidence.json").read_text())
        self.evidence["claims"] = [{"id": "c1", "text": "Fixture design", "status": "proposed", "current": True,
                                    "support": [{"source_id": "s1", "kind": "proposal", "locator": "fixture outline"}]}]
        self.run["questions"][0].update(status="answered", claim_ids=["c1"], gaps=[])

    def report(self, text="Fixture report\n", name="background.md"):
        path = self.root / name
        path.write_text(text)
        self.run["artifacts"][name] = {"path": name, "sha256": digest(path)}
        return path


class LedgerScenarios(LedgerFixture):
    def test_context_switch_requires_a_new_probe(self):
        self.probe()
        for key, value in (("runner", "python-wrapper"), ("sandbox", "escalated"), ("profile", "other-account")):
            request = copy.deepcopy(self.request)
            request["execution_context"][key] = value
            with self.assertRaisesRegex(ValueError, "unverified"):
                state.prepare(self.root, self.run, request)
        request = copy.deepcopy(self.request)
        request["execution_context"]["sandbox"] = "escalated"
        self.complete(state.prepare(self.root, self.run, request, probe=True))
        state.prepare(self.root, self.run, request)

    def test_pending_or_failed_probe_blocks_batches(self):
        p = state.prepare(self.root, self.run, self.request, probe=True)
        with self.assertRaisesRegex(ValueError, "single probe"):
            state.prepare(self.root, self.run, self.request)
        self.complete(p, {"ok": False, "data": None}, "Keychain unavailable", 1)
        with self.assertRaisesRegex(ValueError, "unverified"):
            state.prepare(self.root, self.run, self.request)
        self.assertEqual("failed", self.run["calls"][0]["outcome"])

    def test_failure_then_success_preserves_both_raw_receipts(self):
        first = state.prepare(self.root, self.run, self.request, probe=True)
        self.complete(first, {"ok": False}, "Keychain denied", 1)
        original = (self.root / self.run["calls"][0]["stderr"]["path"]).read_bytes()
        second = self.probe()
        self.assertNotEqual(first["call_id"], second["call_id"])
        self.assertEqual(original, (self.root / self.run["calls"][0]["stderr"]["path"]).read_bytes())
        with self.assertRaisesRegex(ValueError, "sealed"):
            self.complete(first)

    def test_object_403_does_not_revoke_auth_but_keychain_error_does(self):
        self.probe()
        self.complete(state.prepare(self.root, self.run, self.request), {"ok": False, "identity": "user", "error": "403 forbidden"}, code=1)
        next_call = state.prepare(self.root, self.run, self.request)
        self.complete(next_call, {"ok": False}, "Keychain failed", 1)
        with self.assertRaisesRegex(ValueError, "unverified"):
            state.prepare(self.root, self.run, self.request)

    def test_successful_document_about_auth_errors_does_not_revoke_probe(self):
        self.probe()
        self.complete(state.prepare(self.root, self.run, self.request), {"ok": True, "identity": "user", "data": {"document": {"content": "Keychain and invalid token troubleshooting"}}})
        state.prepare(self.root, self.run, self.request)

    def test_unauthorized_and_expired_credentials_require_a_fresh_probe(self):
        for error in ("HTTP 401 Unauthorized", {"status_code": 401}, {"code": "401"},
                      "invalid_grant", "access_token_expired"):
            with self.subTest(error=error):
                self.probe()
                self.complete(state.prepare(self.root, self.run, self.request),
                              {"ok": False, "identity": "user", "error": error}, code=1)
                with self.assertRaisesRegex(ValueError, "unverified"):
                    state.prepare(self.root, self.run, self.request)

    def test_connection_failures_require_a_fresh_probe(self):
        for diagnostic in ("Connection refused", "ECONNRESET", "getaddrinfo EAI_AGAIN",
                           "Could not resolve host", "Connection timed out", "Network is unreachable"):
            with self.subTest(diagnostic=diagnostic):
                self.probe()
                self.complete(state.prepare(self.root, self.run, self.request),
                              {"ok": False, "identity": "user"}, diagnostic, 1)
                with self.assertRaisesRegex(ValueError, "unverified"):
                    state.prepare(self.root, self.run, self.request)

    def test_pending_success_cannot_restore_a_probe_revoked_by_auth_failure(self):
        self.probe()
        failing = state.prepare(self.root, self.run, self.request)
        pending = state.prepare(self.root, self.run, self.request)
        self.complete(failing, {"ok": False, "identity": "user", "status_code": 401}, code=1)
        self.complete(pending)
        with self.assertRaisesRegex(ValueError, "unverified"):
            state.prepare(self.root, self.run, self.request)
        self.probe()
        self.complete(state.prepare(self.root, self.run, self.request))

    def test_wrong_identity_and_invalid_json_are_not_success(self):
        p = state.prepare(self.root, self.run, self.request, probe=True)
        self.assertEqual("failed", self.complete(p, {"ok": True, "identity": "bot"})["outcome"])
        p = state.prepare(self.root, self.run, self.request, probe=True)
        (self.root / p["capture_stdout"]).write_text("not json")
        (self.root / p["capture_stderr"]).write_text("")
        result = state.finish(self.root, self.run, p["call_id"], p["capture_stdout"], p["capture_stderr"], 0)
        self.assertEqual("failed", result["outcome"])

    def test_discovery_is_single_bounded_and_does_not_unlock_batch(self):
        request = copy.deepcopy(self.request)
        request.update(argv=["lark-cli", "docs", "+search", "--query", "fixture", "--as", "user"], discovery_reason="No seed token")
        self.complete(state.prepare(self.root, self.run, request, probe=True))
        with self.assertRaisesRegex(ValueError, "unverified"):
            state.prepare(self.root, self.run, self.request)
        with self.assertRaisesRegex(ValueError, "only one"):
            state.prepare(self.root, self.run, request, probe=True)
        self.probe()
        state.prepare(self.root, self.run, self.request)

    def test_complete_argv_and_read_times_are_preserved(self):
        self.fact()
        c, s = self.run["calls"][0], self.evidence["sources"][0]
        self.assertEqual(self.request["argv"], c["argv"])
        self.assertEqual(c["finished_at"], s["fetched_at"])
        self.assertGreaterEqual(checks.stamp(s["recorded_at"]), checks.stamp(s["fetched_at"]))
        self.assertEqual([], checks.validate(self.run, self.evidence))
        s["fetched_at"] = "2020-01-01T00:00:00Z"
        self.assertTrue(checks.validate(self.run, self.evidence))

    def test_full_read_requires_reason_and_questions(self):
        self.probe()
        request = copy.deepcopy(self.request)
        request["argv"][request["argv"].index("outline")] = "full"
        with self.assertRaisesRegex(ValueError, "full_read_reason"):
            state.prepare(self.root, self.run, request)
        request["full_read_reason"] = "A short full document is needed for q1"
        request["question_ids"] = []
        with self.assertRaisesRegex(ValueError, "question_ids"):
            state.prepare(self.root, self.run, request)
        request["question_ids"] = ["q1"]
        state.prepare(self.root, self.run, request)

    def test_excerpt_is_bounded_and_marks_unread_content(self):
        (self.root / "large.json").write_text(json.dumps({"data": {"document": {"content": "<p>architecture " + "x" * 140000 + "</p>"}}}))
        result = state.excerpt(self.root, "large.json", ["architecture"], 600)
        self.assertLessEqual(len(result["excerpt"]), 600)
        self.assertTrue(result["truncated"])
        with self.assertRaises(ValueError):
            state.excerpt(self.root, "large.json", ["architecture"], 13000)

    def test_pause_resume_excludes_wait_and_preserves_phase_time(self):
        self.run["clock"] = {"segments": [], "running": None}
        with patch.object(state, "now", side_effect=["2026-01-01T00:00:00Z", "2026-01-01T00:00:20Z", "2026-01-01T01:00:00Z", "2026-01-01T01:00:10Z"]):
            state.clock(self.run, "start", "collection")
            state.clock(self.run, "pause", reason="waiting for user")
            state.clock(self.run, "resume", "delivery")
            state.clock(self.run, "pause", reason="finished")
        self.assertEqual({"collection": 20, "delivery": 10}, checks.active_seconds(self.run))
        self.assertEqual([], checks.validate(self.run, self.evidence))
        self.run["clock"]["segments"][1]["started_at"] = "2026-01-01T00:00:10Z"
        self.assertTrue(checks.validate(self.run, self.evidence))

    def test_budget_cannot_be_silently_raised_after_work(self):
        plan = {"authority": "default", "reason": "complex task", "limits": copy.deepcopy(self.run["limits"])}
        state.set_budget(self.run, plan)
        with self.assertRaises(ValueError):
            state.set_budget(self.run, plan)
        plan["authority"] = "user"
        with self.assertRaises(ValueError):
            state.set_budget(self.run, plan)
        plan["user_instruction"] = "fixture user instruction: increase budget"
        state.set_budget(self.run, plan)
        self.assertEqual("user_hard", self.run["budget_policy"])
        plan["limits"]["collection"]["calls"] = 999
        with self.assertRaises(ValueError):
            state.set_budget(self.run, plan)

    def test_concurrent_reservations_cannot_overspend_remaining_call(self):
        self.probe()
        self.run["limits"]["total"]["calls"] = 2
        self.save()
        request_file = self.root / "request.json"
        state.save(request_file, self.request)
        argv = [sys.executable, str(SCRIPTS / "run_state.py"), "prepare", str(self.root), "--file", str(request_file)]
        procs = [subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        outputs = [p.communicate(timeout=15) for p in procs]
        self.assertEqual([0, 1], sorted(p.returncode for p in procs), outputs)
        saved = json.loads((self.root / "run.json").read_text())
        self.assertEqual(2, len(saved["calls"]))

    def test_no_call_can_start_on_paused_or_exhausted_clock(self):
        state.clock(self.run, "pause", reason="paused")
        with self.assertRaisesRegex(ValueError, "clock"):
            state.prepare(self.root, self.run, self.request, probe=True)
        state.clock(self.run, "resume", "collection")
        self.run["limits"]["total"]["seconds"] = 0
        with self.assertRaisesRegex(ValueError, "budget exhausted"):
            state.prepare(self.root, self.run, self.request, probe=True)

    def test_missing_files_hash_changes_and_broken_code_links_fail(self):
        self.fact()
        self.run["artifacts"]["missing"] = {"path": "missing.md", "sha256": "a" * 64}
        result = assess(self.root, self.run, self.evidence, checks.validate)
        self.assertTrue(result["record_valid"])
        self.assertFalse(result["artifacts_valid"])
        self.run["artifacts"] = {}
        report = self.report()
        report.write_text("changed")
        self.assertTrue(check_files(self.root, self.run, self.evidence)[0])
        code = self.root / "file.py"
        code.write_text("line one\n")
        self.report(f"[bad line]({code}:2)\n[missing](missing.py)\n")
        errors, _ = check_files(self.root, self.run, self.evidence)
        self.assertEqual(2, len(errors), errors)

    def test_cache_corruption_is_detected(self):
        self.fact()
        (self.root / self.evidence["sources"][0]["cache"]).write_text("corrupt")
        self.assertTrue(check_files(self.root, self.run, self.evidence)[0])

    def test_recorded_success_must_match_actual_response(self):
        self.fact()
        self.run["calls"][0]["exit_code"] = 1
        errors, _ = check_files(self.root, self.run, self.evidence)
        self.assertTrue(any("outcome disagrees" in e for e in errors))

    def test_requested_outputs_cannot_be_skipped_by_complete_flag(self):
        self.fact()
        self.report()
        self.run["delivery"].update(read_only=False, document=True, html=True)
        result = assess(self.root, self.run, self.evidence, checks.validate)
        self.assertFalse(result["delivery_complete"])
        self.assertEqual(["requested local HTML", "requested document receipt"], result["delivery_missing"])

    def test_budget_at_limit_and_overrun_are_distinguished(self):
        self.run["clock"] = {"running": None, "segments": [{"phase": "collection", "started_at": "2026-01-01T00:00:00Z", "ended_at": "2026-01-01T00:10:00Z", "reason": "handoff"}]}
        result = assess(self.root, self.run, self.evidence, checks.validate)
        self.assertEqual("stop_phase_budget", result["budget_status"]["collection"])
        self.assertTrue(result["budget_compliant"])
        self.run["clock"]["segments"][0]["ended_at"] = "2026-01-01T00:10:01Z"
        result = assess(self.root, self.run, self.evidence, checks.validate)
        self.assertFalse(result["budget_compliant"])
        self.assertEqual(["collection"], result["budget_overrun_phases"])

    def test_missing_legacy_hash_is_not_reported_as_corruption(self):
        self.run["schema_version"] = self.evidence["schema_version"] = 1
        (self.root / "old.raw").write_text("old content")
        self.evidence["sources"] = [{"id": "legacy", "cache": "old.raw"}]
        errors, _ = check_files(self.root, self.run, self.evidence)
        self.assertIn("SHA-256 not recorded", errors[0])

    def test_path_traversal_and_symlink_escape_are_rejected(self):
        for path in ("../outside", str(self.root / "inside")):
            with self.assertRaises(ValueError):
                local_path(self.root, path)
        (self.root / "escape").symlink_to(self.root.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            local_path(self.root, "escape/outside")

    def test_complete_requires_question_coverage_and_no_pending_calls(self):
        self.report()
        result = assess(self.root, self.run, self.evidence, checks.validate)
        self.assertTrue(result["record_valid"])
        self.assertFalse(result["delivery_complete"])
        self.fact()
        self.assertTrue(assess(self.root, self.run, self.evidence, checks.validate)["delivery_complete"])
        self.run["questions"][0]["requires"].append("code")
        self.assertFalse(coverage(self.run, self.evidence)["complete"])
        self.run["questions"][0]["requires"] = ["document"]
        state.prepare(self.root, self.run, self.request)
        self.assertFalse(assess(self.root, self.run, self.evidence, checks.validate)["delivery_complete"])

    def test_superseded_claim_does_not_cover_current_question(self):
        self.fact()
        self.evidence["claims"][0]["current"] = False
        self.assertFalse(coverage(self.run, self.evidence)["complete"])
        self.run["questions"][0]["time_scope"] = "historical"
        self.assertTrue(coverage(self.run, self.evidence)["complete"])

    def test_optional_tiers_still_require_evidence_applicable_to_the_question(self):
        self.fact()
        self.report()
        for omit_requires in (False, True):
            with self.subTest(omit_requires=omit_requires):
                question = self.run["questions"][0]
                question.update(requires=[], time_scope="current")
                if omit_requires:
                    question.pop("requires")
                self.evidence["claims"][0]["current"] = False
                result = assess(self.root, self.run, self.evidence, checks.validate)
                self.assertTrue(result["record_valid"])
                self.assertTrue(result["artifacts_valid"])
                self.assertFalse(result["question_coverage"]["complete"])
                self.assertFalse(result["delivery_complete"])
                self.assertEqual([], result["question_coverage"]["questions"][0]["supported_claim_ids"])
                question["time_scope"] = "historical"
                self.assertTrue(assess(self.root, self.run, self.evidence, checks.validate)["delivery_complete"])
                question["time_scope"] = "current"
                self.evidence["claims"][0]["current"] = True
                self.assertTrue(assess(self.root, self.run, self.evidence, checks.validate)["delivery_complete"])

    def test_optional_tiers_do_not_allow_missing_or_unreadable_support(self):
        self.fact()
        question = self.run["questions"][0]
        question["requires"] = []
        question["claim_ids"] = []
        self.assertFalse(coverage(self.run, self.evidence)["complete"])
        question["claim_ids"] = ["c1"]
        self.evidence["sources"][0]["access"] = "denied"
        self.assertFalse(coverage(self.run, self.evidence)["complete"])
        self.evidence["sources"][0]["access"] = "readable"
        self.evidence["claims"][0]["support"] = []
        self.assertFalse(coverage(self.run, self.evidence)["complete"])

    def test_cli_lifecycle_with_synthetic_native_receipt(self):
        self.save()
        request_file = self.root / "request.json"
        state.save(request_file, self.request)
        result = self.invoke("prepare", "--file", str(request_file), "--probe")
        self.assertEqual(0, result.returncode, result.stderr)
        p = json.loads(result.stdout)
        (self.root / p["capture_stdout"]).write_text(json.dumps({"ok": True, "identity": "user", "data": {"document": {"content": "Fixture heading", "revision_id": 1}}}))
        (self.root / p["capture_stderr"]).write_text("")
        result = self.invoke("finish", "--call-id", p["call_id"], "--stdout", p["capture_stdout"], "--stderr", p["capture_stderr"], "--exit-code", "0")
        self.assertEqual(0, result.returncode, result.stderr)
        result = self.invoke("source", "--call-id", p["call_id"], "--id", "s1", "--locator", "fixture:doc#heading", "--scope", "outline")
        self.assertEqual(0, result.returncode, result.stderr)
        evidence = json.loads((self.root / "evidence.json").read_text())
        evidence["claims"] = [{"id": "c1", "text": "Fixture heading exists", "status": "unknown", "current": True,
                              "support": [{"source_id": "s1", "kind": "context", "locator": "heading"}]}]
        state.save(self.root / "evidence.json", evidence)
        self.run["questions"][0].update(status="answered", claim_ids=["c1"], gaps=[])
        state.save(self.root / "questions.json", self.run["questions"])
        self.assertEqual(0, self.invoke("questions", "--file", str(self.root / "questions.json")).returncode)
        (self.root / "background.md").write_text("Fixture heading exists ([source](https://example.invalid/doc)).\n")
        self.assertEqual(0, self.invoke("artifact", "--id", "report", "--file", "background.md").returncode)
        self.assertEqual(0, self.invoke("clock", "--clock-action", "pause", "--reason", "finished").returncode)
        result = subprocess.run([sys.executable, str(SCRIPTS / "check_artifacts.py"), "check", str(self.root)], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(json.loads(result.stdout)["delivery_complete"])

    def test_unverified_mermaid_is_not_complete_and_stale_receipt_fails(self):
        self.fact()
        self.report("graph LR\n  A-->B\n", "architecture.mmd")
        result = assess(self.root, self.run, self.evidence, checks.validate)
        self.assertFalse(result["delivery_complete"])
        self.assertEqual("not_checked", result["diagrams"][0]["status"])
        self.run["artifacts"]["architecture.mmd"]["mermaid"] = {"status": "passed", "sha256": "a" * 64, "parser": "fixture"}
        self.assertTrue(check_files(self.root, self.run, self.evidence)[0])

    @unittest.skipUnless(shutil.which("node"), "Node unavailable; parser adapter not exercised")
    def test_mermaid_adapter_pass_fail_and_unavailable_with_stub_only(self):
        # This tests the adapter, not actual Mermaid syntax or rendering.
        module = self.root / "stub.mjs"
        module.write_text('export default {parse: async s => {if(s.includes("fixture-invalid")) throw Error("fixture rejection"); return true;}};')
        self.report("fixture-valid", "architecture.mmd")
        self.save()
        result = self.invoke("mermaid", "--id", "architecture.mmd", "--mermaid-module", str(module))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("passed", json.loads(result.stdout)["status"])
        (self.root / "architecture.mmd").write_text("fixture-invalid")
        result = self.invoke("mermaid", "--id", "architecture.mmd", "--mermaid-module", str(module))
        self.assertEqual("failed", json.loads(result.stdout)["status"])
        result = self.invoke("mermaid", "--id", "architecture.mmd", "--mermaid-module", str(self.root / "absent.mjs"))
        self.assertEqual("not_checked", json.loads(result.stdout)["status"])

    def test_v1_is_auditable_but_not_silently_upgraded(self):
        self.run["schema_version"] = self.evidence["schema_version"] = 1
        self.report()
        self.save()
        result = assess(self.root, self.run, self.evidence, checks.validate)
        self.assertTrue(any("Legacy v1" in w for w in result["warnings"]))
        original = (self.root / "run.json").read_bytes()
        self.assertNotEqual(0, self.invoke("status").returncode)
        self.assertEqual(original, (self.root / "run.json").read_bytes())


class VersionEvidenceScenarios(LedgerFixture):
    def code_fact(self):
        self.evidence["sources"] = []
        code = self.root / "service.py"
        code.write_text("def handle():\n    return 1\n")
        ts = state.now()
        self.run["repositories"] = [{"id": "r1", "path": str(self.root), "head": "a" * 40,
                                      "branch": "main", "dirty": False, "observed_at": ts}]
        self.evidence["sources"] = [{"id": "s1", "kind": "code", "access": "readable", "locator": str(code) + ":1",
            "observed_at": ts, "fetched_at": ts, "recorded_at": ts, "provenance": "direct", "repository_id": "r1",
            "commit": "a" * 40, "file": "service.py", "line": 1, "sha256": digest(code)}]
        self.evidence["claims"] = [{"id": "c1", "text": "Handler exists", "status": "implemented", "current": True,
            "implementation_scope": "local_snapshot", "support": [{"source_id": "s1", "kind": "implementation", "locator": "service.py:1 handle"}]}]

    def test_current_code_requires_matching_branch_receipt_and_clean_tree(self):
        self.code_fact()
        self.assertEqual([], checks.validate(self.run, self.evidence))
        claim = self.evidence["claims"][0]
        claim["implementation_scope"] = "current_code"
        self.assertTrue(checks.validate(self.run, self.evidence))
        receipt = self.root / "remote.txt"
        receipt.write_text("a" * 40 + "\trefs/heads/main\n")
        repo = self.run["repositories"][0]
        repo.update(remote_head="a" * 40, remote_ref="refs/heads/main", remote_receipt=str(receipt), remote_receipt_sha256=digest(receipt))
        self.assertEqual([], checks.validate(self.run, self.evidence))
        self.assertEqual([], check_files(self.root, self.run, self.evidence)[0])
        for key, val in (("dirty", True), ("remote_head", "b" * 40), ("remote_ref", "refs/heads/old")):
            previous = repo[key]
            repo[key] = val
            self.assertTrue(checks.validate(self.run, self.evidence))
            repo[key] = previous

    def test_wrong_code_commit_line_or_changed_file_is_detected(self):
        self.code_fact()
        source = self.evidence["sources"][0]
        source["commit"] = "b" * 40
        self.assertTrue(checks.validate(self.run, self.evidence))
        source["commit"] = "a" * 40
        source["line"] = 999
        self.assertTrue(check_files(self.root, self.run, self.evidence)[0])
        source["line"] = 1
        (self.root / "service.py").write_text("changed\n")
        self.assertTrue(check_files(self.root, self.run, self.evidence)[0])

    def test_message_claiming_deployed_is_not_direct_runtime_evidence(self):
        self.fact()
        self.evidence["claims"][0].update(status="operating")
        self.evidence["claims"][0]["support"][0]["kind"] = "runtime"
        self.evidence["sources"][0].update(kind="message", provenance="secondary")
        self.assertTrue(checks.validate(self.run, self.evidence))
        self.evidence["sources"][0].update(kind="runtime", provenance="direct", environment="fixture-prod",
                                          deployment_revision="fixture-release", trace_locator="fixture:trace/1")
        self.assertEqual([], checks.validate(self.run, self.evidence))


if __name__ == "__main__":
    unittest.main()
