"""Workflow regressions using captured synthetic responses; never contacts Lark."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from test_run_state import LedgerFixture
import check_artifacts as checks
import run_state as state
from record_validation import assess, digest
from workflow import apply_updates, collection_coverage, delivery_checks, operation


class WorkflowScenarios(LedgerFixture):
    def request(self, argv, response, *, probe=False, phase="collection", code=0):
        request = copy.deepcopy(self.request_template)
        request.update(argv=["lark-cli", *argv, "--as", "user"], phase=phase)
        reservation = state.prepare(self.root, self.run, request, probe=probe)
        self.complete(reservation, response, code=code)
        return reservation["call_id"]

    def setUp(self):
        super().setUp()
        # The inherited fixture has a self.request dictionary; keep the helper name callable.
        self.request_template = self.request
        del self.request

    def test_chat_only_task_uses_real_message_evidence_without_document_probe(self):
        self.run["questions"][0]["requires"] = ["message"]
        cid = self.request(["im", "+messages-search", "--query", "Atlas"],
                           {"ok": True, "identity": "user", "data": {"items": [{"text": "Review chose B"}]}}, probe=True)
        apply_updates(self.run, self.evidence, {
            "sources": [{"id": "msg1", "call_id": cid, "kind": "message", "locator": "https://example.invalid/chat/message1", "scope": "message"}],
            "claims": [{"id": "c1", "text": "Review chose B", "status": "decided", "current": True,
                        "support": [{"source_id": "msg1", "kind": "decision", "locator": "message1"}]}],
            "questions": [{"id": "q1", "text": "What was decided?", "requires": ["message"], "status": "answered", "claim_ids": ["c1"], "gaps": []}]})
        self.report("Review chose B [source](https://example.invalid/chat/message1)\n")
        self.assertTrue(assess(self.root, self.run, self.evidence, checks.validate)["delivery_complete"])
        self.assertTrue(all(c["argv"][1] == "im" for c in self.run["calls"]))

    def test_empty_document_search_does_not_block_chat_seed(self):
        self.request(["docs", "+search", "--query", "Atlas"], {"ok": True, "identity": "user", "data": {"items": []}}, probe=True)
        cid = self.request(["im", "+chat-search", "--query", "Atlas"], {"ok": True, "identity": "user", "data": {"items": []}}, probe=True)
        self.assertEqual("success", self.run["calls"][-1]["outcome"])
        self.assertTrue(cid)

    def test_domain_scope_change_requires_its_own_probe(self):
        self.probe_with_helper()
        with self.assertRaisesRegex(ValueError, "unverified"):
            self.request(["minutes", "+search", "--query", "Atlas"], {}, probe=False)
        self.request(["minutes", "+search", "--query", "Atlas"], {"ok": True, "identity": "user", "data": {}}, probe=True)

    def probe_with_helper(self):
        return self.request(["docs", "+fetch", "--doc", "fixture-doc", "--scope", "outline"],
                            {"ok": True, "identity": "user", "data": {"document": {"revision_id": 7, "content": "Fixture design"}}}, probe=True)

    def test_probe_cannot_write_or_fetch_unbounded_transcript(self):
        for argv in (["im", "+messages-search", "--page-all"], ["minutes", "+detail", "--transcript"], ["apps", "+create"]):
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                self.request(argv, {}, probe=True)

    def test_failed_batch_is_atomic(self):
        before = copy.deepcopy((self.run, self.evidence))
        with self.assertRaises(ValueError):
            apply_updates(self.run, self.evidence, {"questions": [{"id": "q2", "text": "bad", "status": "answered", "claim_ids": ["missing"]}]})
        self.assertEqual(before, (self.run, self.evidence))

    def test_finish_and_batch_update_use_single_local_command(self):
        request = self.request_template
        reservation = state.prepare(self.root, self.run, request, probe=True)
        self.save()
        (self.root / reservation["capture_stdout"]).write_text(json.dumps({"ok": True, "identity": "user", "data": {}}))
        (self.root / reservation["capture_stderr"]).write_text("")
        state.save(self.root / "update.json", {"sources": [{"id": "s1", "kind": "document", "locator": "fixture:doc", "scope": "outline"}]})
        result = self.invoke("finish", "--call-id", reservation["call_id"], "--stdout", reservation["capture_stdout"],
                             "--stderr", reservation["capture_stderr"], "--exit-code", "0", "--update-file", str(self.root / "update.json"))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(reservation["call_id"], json.loads((self.root / "evidence.json").read_text())["sources"][0]["call_id"])

    def test_invalid_optional_update_does_not_lose_executed_call_receipt(self):
        reservation = state.prepare(self.root, self.run, self.request_template, probe=True)
        self.save()
        (self.root / reservation["capture_stdout"]).write_text(json.dumps({"ok": True, "identity": "user", "data": {}}))
        (self.root / reservation["capture_stderr"]).write_text("")
        state.save(self.root / "bad.json", {"claims": [{"id": "bad", "text": "unfounded", "status": "decided", "current": True, "support": []}]})
        result = self.invoke("finish", "--call-id", reservation["call_id"], "--stdout", reservation["capture_stdout"],
                             "--stderr", reservation["capture_stderr"], "--exit-code", "0", "--update-file", str(self.root / "bad.json"))
        self.assertEqual(1, result.returncode)
        self.assertEqual("success", json.loads((self.root / "run.json").read_text())["calls"][0]["outcome"])

    def test_interrupted_batch_journal_rolls_forward_under_lock(self):
        self.save()
        candidate = copy.deepcopy(self.run)
        candidate["pending_leads"] = ["specific lead"]
        state.save(self.root / ".ledger-transaction.json", {"run": candidate, "evidence": self.evidence})
        with state.ledger(self.root) as recovered:
            self.assertEqual(["specific lead"], recovered["pending_leads"])
        self.assertFalse((self.root / ".ledger-transaction.json").exists())

    def test_full_background_requires_domains_prehistory_and_discussion_assessment(self):
        self.run["coverage_scope"] = "full"
        self.assertFalse(collection_coverage(self.run)["complete"])
        apply_updates(self.run, self.evidence, {"coverage": {
            key: {"status": "skipped", "reason": "Explicitly excluded by synthetic user request", "call_ids": []}
            for key in ("documents", "chats", "messages", "meetings", "prehistory", "decision_discussion")}})
        self.assertTrue(collection_coverage(self.run)["complete"])
        self.run["coverage"]["prehistory"] = {"status": "partial", "reason": "Budget exhausted", "call_ids": []}
        self.assertFalse(collection_coverage(self.run)["complete"])

    def test_coverage_cannot_claim_message_search_from_document_call(self):
        cid = self.probe_with_helper()
        with self.assertRaisesRegex(ValueError, "unrelated"):
            apply_updates(self.run, self.evidence, {"coverage": {"messages": {"status": "examined", "reason": "Checked", "call_ids": [cid]}}})

    def document_ready(self):
        cid = self.probe_with_helper()
        self.save()
        state.source(self.root, self.run, type("Args", (), {"call_id": cid, "id": "s1", "kind": "document", "locator": "https://example.invalid/seed", "scope": "outline", "provenance": "primary"})())
        self.evidence = json.loads((self.root / "evidence.json").read_text())
        apply_updates(self.run, self.evidence, {
            "claims": [{"id": "c1", "text": "Review chose B", "status": "decided", "current": True,
                        "support": [{"source_id": "s1", "kind": "decision", "locator": "decision paragraph"}]}],
            "questions": [{"id": "q1", "text": "What is decided?", "status": "answered", "claim_ids": ["c1"], "gaps": [], "requires": ["document"]}]})
        self.report("Review chose B\n")
        self.report("<document><p>Review chose B</p></document>", "background.xml")
        self.run["delivery"].update(document=True, read_only=False)
        state.clock(self.run, "pause", reason="collection finished")
        state.clock(self.run, "resume", phase="delivery")
        operation(self.root, self.run, {"kind": "document", "action": "start", "artifact_ids": ["background.xml", "background.md"]})
        cid = self.request(["docs", "+create", "--content", "@background.xml"],
                           {"ok": True, "identity": "user", "data": {"document_id": "fixture-doc", "url": "https://example.invalid/doc"}}, phase="delivery")
        operation(self.root, self.run, {"kind": "document", "action": "result", "status": "succeeded", "call_id": cid,
                                       "receipt": {"id": "fixture-doc", "url": "https://example.invalid/doc"}})

    def verify_document(self, text="Review chose B", doc="fixture-doc"):
        cid = self.request(["docs", "+fetch", "--doc", doc, "--scope", "keyword"],
                           {"ok": True, "identity": "user", "data": {"document": {"revision_id": 8, "content": text}}}, phase="delivery")
        return operation(self.root, self.run, {"kind": "document", "action": "verify", "call_id": cid, "checks": ["Review chose B"]})

    def test_remote_success_requires_current_version_readback(self):
        self.document_ready()
        self.assertFalse(assess(self.root, self.run, self.evidence, checks.validate)["delivery_complete"])
        self.verify_document()
        self.assertTrue(assess(self.root, self.run, self.evidence, checks.validate)["delivery_complete"])
        self.report("<document><p>Version B updated later</p></document>", "background.xml")
        result = assess(self.root, self.run, self.evidence, checks.validate)
        self.assertFalse(result["delivery_complete"])
        self.assertTrue(any("changed" in s for s in result["delivery_missing"]))

    def test_create_argv_cannot_reference_another_input_file(self):
        self.document_ready()
        self.run["operations"]["document"][-1]["status"] = "inflight"
        with self.assertRaisesRegex(ValueError, "bound input"):
            self.request(["docs", "+create", "--content", "@other.xml"], {}, phase="delivery")

    def test_same_inflight_write_cannot_be_reserved_twice(self):
        self.document_ready()
        self.run["operations"]["document"][-1]["status"] = "inflight"
        with self.assertRaisesRegex(ValueError, "already reserved"):
            self.request(["docs", "+create", "--content", "@background.xml"], {}, phase="delivery")

    def test_unknown_document_is_reconciled_by_readback_without_second_create(self):
        self.document_ready()
        item = self.run["operations"]["document"][-1]
        item["status"] = "unknown"
        item["receipt"] = {}
        cid = self.request(["docs", "+fetch", "--doc", "fixture-doc", "--scope", "keyword"],
                           {"ok": True, "identity": "user", "data": {"document": {"document_id": "fixture-doc", "url": "https://example.invalid/doc", "revision_id": 8, "content": "Review chose B"}}}, phase="delivery")
        operation(self.root, self.run, {"kind": "document", "action": "result", "status": "succeeded", "reconciled": True,
                                       "reason": "Unique task token and current content matched", "checks": ["Review chose B"], "call_id": cid,
                                       "receipt": {"id": "fixture-doc", "url": "https://example.invalid/doc"}})
        operation(self.root, self.run, {"kind": "document", "action": "verify", "call_id": cid, "checks": ["Review chose B"]})
        self.assertEqual([], delivery_checks(self.root, self.run))
        self.assertEqual(1, len(self.run["operations"]["document"]))

    def test_unrelated_or_mismatching_readback_cannot_verify_document(self):
        self.document_ready()
        with self.assertRaisesRegex(ValueError, "another object"):
            self.verify_document(doc="other-doc")
        with self.assertRaisesRegex(ValueError, "actual returned"):
            self.verify_document(text="Different contents")

    def test_unknown_write_cannot_be_retried(self):
        self.document_ready()
        op = self.run["operations"]["document"][-1]
        op["status"] = "unknown"
        with self.assertRaisesRegex(ValueError, "reconcile"):
            operation(self.root, self.run, {"kind": "document", "action": "start", "artifact_ids": ["background.xml"]})

    def test_read_only_cannot_prepare_remote_writes(self):
        self.probe_with_helper()
        with self.assertRaisesRegex(ValueError, "authorized delivery"):
            self.request(["docs", "+create"], {}, phase="collection")

    def test_publish_requires_visibility_from_actual_receipt(self):
        self.probe_with_helper()
        self.run["delivery"].update(read_only=False, publish=True, html=True)
        self.report("<html>Fixture</html>", "index.html")
        state.clock(self.run, "pause", reason="collection finished")
        state.clock(self.run, "resume", phase="delivery")
        operation(self.root, self.run, {"kind": "app", "action": "start", "artifact_ids": ["index.html"]})
        cid = self.request(["apps", "+create"], {"ok": True, "identity": "user", "data": {"app": {"app_id": "app_fixture"}}}, phase="delivery")
        operation(self.root, self.run, {"kind": "app", "action": "result", "status": "succeeded", "call_id": cid, "receipt": {"id": "app_fixture"}})
        with self.assertRaisesRegex(ValueError, "visibility"):
            operation(self.root, self.run, {"kind": "publish", "action": "start", "artifact_ids": ["index.html"]})
        cid = self.request(["apps", "+access-scope-get", "--app-id", "app_fixture"],
                           {"ok": True, "identity": "user", "data": {"scope": "tenant"}}, probe=True, phase="delivery")
        with self.assertRaisesRegex(ValueError, "authorized audience"):
            operation(self.root, self.run, {"kind": "app", "action": "verify", "call_id": cid, "checks": ["tenant"], "visibility_locator": "data.scope"})
        cid = self.request(["apps", "+access-scope-get", "--app-id", "app_fixture"],
                           {"ok": True, "identity": "user", "data": {"scope": "creator"}}, phase="delivery")
        operation(self.root, self.run, {"kind": "app", "action": "verify", "call_id": cid, "checks": ["creator"], "visibility_locator": "data.scope"})
        operation(self.root, self.run, {"kind": "publish", "action": "start", "artifact_ids": ["index.html"]})
        cid = self.request(["apps", "+html-publish", "--app-id", "app_fixture", "--path", "index.html"],
                           {"ok": True, "identity": "user", "data": {"release_id": "release_fixture"}}, phase="delivery")
        operation(self.root, self.run, {"kind": "publish", "action": "result", "status": "submitted", "call_id": cid, "receipt": {"release_id": "release_fixture"}})
        wrong = self.request(["apps", "+release-get", "--app-id", "app_fixture", "--release-id", "other_release"],
                             {"ok": True, "identity": "user", "data": {"status": "finished", "online_url": "https://example.invalid/live"}}, phase="delivery")
        with self.assertRaisesRegex(ValueError, "another object"):
            operation(self.root, self.run, {"kind": "publish", "action": "result", "status": "succeeded", "call_id": wrong, "receipt": {"url": "https://example.invalid/live"}})
        cid = self.request(["apps", "+release-get", "--app-id", "app_fixture", "--release-id", "release_fixture"],
                           {"ok": True, "identity": "user", "data": {"status": "finished", "online_url": "https://example.invalid/live"}}, phase="delivery")
        operation(self.root, self.run, {"kind": "publish", "action": "result", "status": "succeeded", "call_id": cid, "receipt": {"url": "https://example.invalid/live"}})
        self.assertEqual([], delivery_checks(self.root, self.run))


if __name__ == "__main__":
    unittest.main()
