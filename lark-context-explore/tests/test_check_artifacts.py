"""Offline regression cases; no network or real Lark assets are used."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_artifacts.py"
spec = importlib.util.spec_from_file_location("artifact_checks", SCRIPT)
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)
from record_validation import context_key


def bundle(**kwargs):
    run, evidence = checks.initial_state("Atlas", **kwargs)
    ts = "2026-10-15T10:00:00+08:00"
    ctx = {"runner": "fixture", "sandbox": "fixture", "identity": "user"}
    run["calls"] = [{"id": "probe1", "phase": "collection", "command": "fixture probe",
                     "argv": ["lark-cli", "docs", "+fetch", "--scope", "outline", "--as", "user"],
                     "execution_context": ctx, "context_key": context_key(ctx), "is_probe": True,
                     "started_at": ts, "finished_at": ts, "outcome": "success", "exit_code": 0,
                     "stdout": {"path": "fixture.json", "sha256": "a" * 64},
                     "stderr": {"path": "fixture.err", "sha256": "b" * 64}}]
    evidence["sources"] = [{"id": "s1", "kind": "document", "locator": "fixture:review#decision",
                            "access": "readable", "observed_at": ts, "fetched_at": ts,
                            "recorded_at": ts, "provenance": "primary", "call_id": "probe1",
                            "cache": "fixture.json", "sha256": "a" * 64}]
    evidence["claims"] = [{"id": "c1", "text": "Review selected B", "status": "decided",
                           "current": True, "support": [{"source_id": "s1", "kind": "decision",
                                                           "locator": "decision paragraph"}],
                           "supersedes": [], "conflicts_with": []}]
    return run, evidence


def attempt(status, **kwargs):
    return {"status": status, "request_tag": "fixture-run-1", "content_sha256": "a" * 64,
            "receipt": {}, "confirmed_not_applied": False, **kwargs}


def round_(**kwargs):
    return {"branch": "decision-rationale", "new_claim_ids": [], "resolved_questions": [],
            "new_conflicts": [], **kwargs}


class ArtifactScenarios(unittest.TestCase):
    def test_default_background_does_not_request_external_outputs(self):
        run, evidence = bundle()
        self.assertFalse(any(run["delivery"].values()))
        self.assertEqual([], checks.validate(run, evidence))

    def test_read_only_accepts_local_html_but_rejects_remote_attempt(self):
        run, evidence = bundle(read_only=True, html=True)
        self.assertEqual([], checks.validate(run, evidence))
        run["operations"]["document"] = [attempt("inflight")]
        self.assertTrue(checks.validate(run, evidence))
        with self.assertRaises(ValueError):
            checks.initial_state("Atlas", read_only=True, publish=True)

    def test_same_document_new_decision_evidence_keeps_branch_open(self):
        run, evidence = bundle()
        run["rounds"] = [round_(), round_(new_claim_ids=["c1"])]
        self.assertEqual([], checks.validate(run, evidence))
        self.assertEqual("continue_within_budget", checks.branch_status(run, "decision-rationale"))

    def test_more_entities_without_useful_evidence_do_not_extend_search(self):
        run, _ = bundle()
        run["rounds"] = [round_(new_entity_ids=["doc2"]), round_(new_entity_ids=["chat2"])]
        self.assertEqual("pause_no_evidence_gain", checks.branch_status(run, "decision-rationale"))

    def test_resolving_question_or_finding_conflict_is_useful_gain(self):
        for gain in ({"resolved_questions": ["q1"]}, {"new_conflicts": ["conflict1"]}):
            run, _ = bundle()
            run["rounds"] = [round_(), round_(**gain)]
            self.assertEqual("continue_within_budget", checks.branch_status(run, "decision-rationale"))

    def test_concrete_lead_cannot_bypass_total_call_budget(self):
        run, _ = bundle()
        run["limits"]["total"]["calls"] = 2
        run["calls"] = [{"phase": "collection", "command": "docs search", "outcome": "ok"},
                        {"phase": "delivery", "command": "docs fetch", "outcome": "ok"}]
        run["pending_leads"] = ["decision-rationale"]
        self.assertEqual("stop_budget", checks.branch_status(run, "decision-rationale"))
        self.assertEqual("stop_total_budget", checks.budget_status(run, "delivery"))

    def test_collection_time_cap_preserves_delivery_budget(self):
        run, _ = bundle()
        run["clock"]["segments"] = [{"phase": "collection", "started_at": "2026-10-15T00:00:00Z",
                                    "ended_at": "2026-10-15T00:10:00Z", "reason": "handoff"}]
        self.assertEqual("stop_phase_budget", checks.budget_status(run, "collection"))
        self.assertEqual("available", checks.budget_status(run, "delivery"))

    def test_unreadable_sources_cannot_support_factual_conclusions(self):
        for outcome in ("forbidden", "not_found", "missing_scope", "unsupported"):
            run, evidence = bundle()
            evidence["sources"][0]["access"] = outcome
            self.assertTrue(checks.validate(run, evidence))
            evidence["claims"] = []
            self.assertEqual([], checks.validate(run, evidence))

    def test_decision_is_not_proof_of_running_service(self):
        run, evidence = bundle()
        evidence["claims"][0]["status"] = "operating"
        self.assertTrue(checks.validate(run, evidence))
        evidence["claims"][0]["support"][0]["kind"] = "runtime"
        self.assertTrue(checks.validate(run, evidence))
        evidence["sources"][0].update(kind="runtime", provenance="direct", environment="fixture",
                                      deployment_revision="fixture-rev", trace_locator="fixture-trace")
        self.assertEqual([], checks.validate(run, evidence))

    def test_new_decision_supersedes_old_without_erasing_history(self):
        run, evidence = bundle()
        newer = copy.deepcopy(evidence["claims"][0])
        newer.update(id="c2", text="Later decision selected C", supersedes=["c1"])
        evidence["claims"].append(newer)
        self.assertTrue(checks.validate(run, evidence))
        evidence["claims"][0]["current"] = False
        self.assertEqual([], checks.validate(run, evidence))
        self.assertEqual(2, len(evidence["claims"]))

    def test_broken_citations_and_supersession_cycles_are_rejected(self):
        run, evidence = bundle()
        evidence["claims"][0]["support"][0]["source_id"] = "absent"
        self.assertTrue(checks.validate(run, evidence))
        run, evidence = bundle()
        evidence["claims"][0].update(current=False, supersedes=["c1"])
        self.assertTrue(checks.validate(run, evidence))

    def test_timeout_cannot_be_followed_by_another_create(self):
        for status in ("unknown", "inflight", "succeeded"):
            run, evidence = bundle(document=True)
            receipt = {"id": "doc-1", "url": "https://example.invalid/doc/1"}
            run["operations"]["document"] = [attempt(status, receipt=receipt), attempt("inflight")]
            self.assertTrue(checks.validate(run, evidence))

    def test_reconcile_success_updates_original_attempt(self):
        run, evidence = bundle(document=True)
        run["operations"]["document"] = [attempt("unknown")]
        self.assertEqual([], checks.validate(run, evidence))
        run["operations"]["document"][0].update(status="succeeded",
            receipt={"id": "doc-1", "url": "https://example.invalid/doc/1"})
        self.assertEqual([], checks.validate(run, evidence))
        self.assertEqual(1, len(run["operations"]["document"]))

    def test_only_confirmed_not_applied_failure_allows_one_retry(self):
        run, evidence = bundle(publish=True)
        run["operations"]["app"] = [attempt("failed"), attempt("inflight")]
        self.assertTrue(checks.validate(run, evidence))
        run["operations"]["app"][0]["confirmed_not_applied"] = True
        self.assertEqual([], checks.validate(run, evidence))
        run["operations"]["app"].append(attempt("inflight"))
        self.assertTrue(checks.validate(run, evidence))

    def test_submitted_release_is_not_published_and_cannot_be_retried(self):
        run, evidence = bundle(publish=True)
        run["operations"]["publish"] = [attempt("submitted", receipt={"release_id": "rel-1"})]
        self.assertEqual([], checks.validate(run, evidence))
        run["operations"]["publish"].append(attempt("inflight"))
        self.assertTrue(checks.validate(run, evidence))

    def test_publication_failure_preserves_document_success(self):
        run, evidence = bundle(document=True, publish=True)
        run["operations"]["document"] = [attempt("succeeded",
            receipt={"id": "doc-1", "url": "https://example.invalid/doc/1"})]
        run["operations"]["publish"] = [attempt("failed", confirmed_not_applied=True)]
        self.assertEqual([], checks.validate(run, evidence))
        self.assertEqual("succeeded", run["operations"]["document"][0]["status"])

    def test_cli_init_check_and_resume_do_not_overwrite_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            def invoke(*args):
                return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)
            self.assertEqual(0, invoke("init", tmp, "--topic", "Atlas", "--read-only").returncode)
            original = (Path(tmp) / "run.json").read_bytes()
            result = invoke("check", tmp)
            self.assertEqual(0, result.returncode, result.stderr)
            state = json.loads(result.stdout)
            self.assertTrue(state["record_valid"])
            self.assertTrue(state["artifacts_valid"])
            self.assertFalse(state["delivery_complete"])
            self.assertNotIn("valid", state)
            self.assertNotEqual(0, invoke("init", tmp, "--topic", "Other").returncode)
            self.assertEqual(original, (Path(tmp) / "run.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
