"""Exercise the real CLI against synthetic ledgers, never the configured learner data."""
import copy
import shutil
from unittest import mock
from datetime import date, timedelta
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/progress.py"
SPEC = importlib.util.spec_from_file_location("travel_progress", SCRIPT)
progress = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(progress)


def rating(status="需要提示"):
    return {"status": status, "evidence": "Synthetic text fixture: required a sentence opening."}


def session(sid="lesson", status="in_progress"):
    return {"id": sid, "date": "2026-10-16", "status": status, "mode": "text",
            "topic": "Synthetic hotel fixture", "abilities": {"需求": rating()}}


def item(iid="repeat", due="2026-10-23"):
    return {"id": iid, "phrase": "Could you say that again?", "meaning": "请再说一遍",
            "issue": "Synthetic clarification fixture", "next_review": due}


def result(iid="repeat", on="2026-10-16", outcome="独立完成"):
    return {"id": iid, "reviewed_on": on, "result": outcome, "mode": "text",
            "evidence": "Synthetic text fixture: new location, no prompt or model answer."}


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="travel-coach-test-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "ledger"
        self.env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        self.counter = 0
        self.call("init")

    def argv(self, *args):
        return [sys.executable, str(SCRIPT), "--data-dir", str(self.directory), *map(str, args)]

    def call(self, *args, ok=True):
        response = subprocess.run(self.argv(*args), capture_output=True, text=True, env=self.env)
        self.assertEqual(response.returncode == 0, ok, response.stdout + response.stderr)
        return json.loads(response.stdout if ok else response.stderr)

    def read(self):
        return json.loads((self.directory / "progress.json").read_text())

    def put(self, state):
        (self.directory / "progress.json").write_text(json.dumps(state, ensure_ascii=False))

    def patch_file(self, patch):
        self.counter += 1
        path = Path(self.temp.name) / f"patch-{self.counter}.json"
        path.write_text(json.dumps(patch, ensure_ascii=False))
        return path

    def save(self, patch, revision=None, ok=True):
        revision = self.read()["revision"] if revision is None else revision
        return self.call("save", "--file", self.patch_file(patch), "--expected-revision", revision, ok=ok)

    def test_assessment_partial_update_and_explicit_deletion(self):
        self.save({"progress": {"assessment": {"需求": rating(), "澄清": rating()}}})
        self.save({"progress": {"assessment": {"需求": rating("独立完成")}}})
        self.assertEqual(set(self.read()["progress"]["assessment"]), {"需求", "澄清"})
        self.save({"progress": {"assessment": {}}})
        self.assertEqual(len(self.read()["progress"]["assessment"]), 2)
        self.save({"progress": {"assessment": {"澄清": None}}})
        self.assertEqual(set(self.read()["progress"]["assessment"]), {"需求"})

    def test_assessment_requires_matching_evidence_with_each_status(self):
        self.save({"progress": {"assessment": {"需求": rating()}}})
        before = (self.directory / "progress.json").read_bytes()
        self.save({"progress": {"assessment": {"需求": {"status": "独立完成"}}}}, ok=False)
        self.assertEqual((self.directory / "progress.json").read_bytes(), before)

    def test_session_checkpoints_merge_without_duplicate_completion(self):
        self.save({"session": session()})
        self.save({"session": {"id": "lesson", "status": "completed", "abilities": {"澄清": rating()}}})
        self.save({"session": {"id": "lesson", "summary": "Synthetic checkpoint"}})
        view = self.call("show")
        self.assertEqual(view["completed_sessions"], 1)
        self.assertEqual(set(view["recent_sessions"][0]["abilities"]), {"需求", "澄清"})
        self.save({"session": {"id": "lesson", "abilities": {"需求": None}}})
        self.assertEqual(set(self.read()["sessions"]["lesson"]["abilities"]), {"澄清"})

    def test_stale_revision_preserves_current_and_backup(self):
        self.save({"profile": {"daily_minutes": 30}})
        before = [(self.directory / name).read_bytes() for name in ("progress.json", "progress.previous.json")]
        error = self.save({"profile": {"daily_minutes": 45}}, revision=0, ok=False)
        self.assertIn("Revision conflict", error["message"])
        self.assertEqual(before, [(self.directory / name).read_bytes() for name in ("progress.json", "progress.previous.json")])

    def test_concurrent_writers_only_one_can_commit_same_revision(self):
        patches = [self.patch_file({"profile": {"daily_minutes": value}}) for value in (30, 45)]
        processes = [subprocess.Popen(self.argv("save", "--file", path, "--expected-revision", "0"),
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env)
                     for path in patches]
        for process in processes:
            process.communicate(timeout=15)
        self.assertEqual(sorted(p.returncode for p in processes), [0, 1])
        self.assertEqual(self.read()["revision"], 1)
        self.assertEqual(json.loads((self.directory / "progress.previous.json").read_text())["revision"], 0)

    def test_nested_corruption_never_overwrites_healthy_backup(self):
        self.save({"session": session(), "review_items": [item()]})
        healthy = self.read()
        variants = []
        broken = copy.deepcopy(healthy)
        del broken["review_items"]["repeat"]["next_review"]
        variants.append(broken)
        broken = copy.deepcopy(healthy)
        broken["sessions"]["lesson"]["date"] = "invalid"
        variants.append(broken)
        broken = copy.deepcopy(healthy)
        broken["sessions"]["lesson"]["abilities"]["需求"]["evidence"] = ""
        variants.append(broken)
        broken = copy.deepcopy(healthy)
        broken["review_items"]["repeat"]["id"] = "wrong-key"
        variants.append(broken)
        for broken in variants:
            with self.subTest(broken=broken):
                self.put(broken)
                backup = self.directory / "progress.previous.json"
                backup.write_text(json.dumps(healthy, ensure_ascii=False))
                before = [(self.directory / name).read_bytes() for name in ("progress.json", "progress.previous.json")]
                self.call("show", ok=False)
                self.save({"profile": {"daily_minutes": 30}}, ok=False)
                self.assertEqual(before, [(self.directory / name).read_bytes() for name in ("progress.json", "progress.previous.json")])

    def test_invalid_patch_preserves_backup_and_state(self):
        self.save({"review_items": [item()]})
        before = [(self.directory / name).read_bytes() for name in ("progress.json", "progress.previous.json")]
        self.save({"profile": {"daily_minutes": 30}, "review_results": [result(), result("missing")]}, ok=False)
        self.assertEqual(before, [(self.directory / name).read_bytes() for name in ("progress.json", "progress.previous.json")])

    def test_v1_records_remain_readable_without_fabricated_history(self):
        self.save({"review_items": [item()]})
        state = self.read()
        state["review_items"]["repeat"].update({"attempts": 5, "last_result": "独立完成"})
        self.put(state)
        before = (self.directory / "progress.json").read_bytes()
        self.call("show")
        self.assertEqual((self.directory / "progress.json").read_bytes(), before)
        self.save({"profile": {"daily_minutes": 30}})
        review = self.read()["review_items"]["repeat"]
        self.assertEqual(review["attempts"], 5)
        self.assertNotIn("last_reviewed_on", review)
        self.save({"review_results": [result()]})
        review = self.read()["review_items"]["repeat"]
        self.assertEqual(review["attempts"], 6)
        self.assertEqual(review["interval_days"], 1)

    def test_future_review_lookup_and_search(self):
        self.save({"review_items": [item()]})
        self.assertEqual(self.call("show", "--today", "2026-10-16")["due_review_count"], 0)
        for query in ("REPEAT", "SAY THAT", "请再", "clarification"):
            with self.subTest(query=query):
                self.assertEqual(self.call("reviews", "--query", query)["items"][0]["id"], "repeat")
        self.assertEqual(self.call("get", "review", "repeat")["item"]["next_review"], "2026-10-23")
        self.assertEqual(self.call("reviews", "--due", "--today", "2026-10-16")["total"], 0)
        self.assertEqual(self.call("reviews", "--due", "--today", "2026-10-23")["total"], 1)
        self.call("get", "review", "missing", ok=False)

    def test_old_unfinished_session_is_available_beyond_fifty_recent_sessions(self):
        state = self.read()
        for n in range(55):
            record = {**session(f"session-{n:03d}", "in_progress" if n == 0 else "completed"),
                      "updated_at": "2026-10-16T00:00:00+08:00", "minutes": None, "summary": "", "next_step": ""}
            state["sessions"][record["id"]] = record
        self.put(state)
        view = self.call("show")
        self.assertEqual(view["unfinished_sessions"][0]["id"], "session-000")
        self.assertEqual(self.call("sessions", "--status", "in_progress")["items"][0]["id"], "session-000")
        first = self.call("sessions", "--limit", "50")
        second = self.call("sessions", "--limit", "50", "--offset", first["next_offset"])
        self.assertEqual(len(first["items"]) + len(second["items"]), 55)
        self.assertIsNone(second["next_offset"])
        self.assertEqual(self.call("get", "session", "session-000")["item"]["status"], "in_progress")

    def test_review_pagination_covers_all_items(self):
        self.save({"review_items": [item(f"item-{n:03d}") for n in range(61)]})
        first = self.call("reviews", "--limit", "50")
        second = self.call("reviews", "--limit", "50", "--offset", first["next_offset"])
        ids = [row["id"] for row in first["items"] + second["items"]]
        self.assertEqual(len(ids), 61)
        self.assertEqual(len(set(ids)), 61)
        self.assertIsNone(second["next_offset"])
        self.call("reviews", "--offset", "-1", ok=False)
        self.call("sessions", "--limit", "51", ok=False)

    def test_read_commands_do_not_create_a_missing_ledger(self):
        self.directory = Path(self.temp.name) / "missing"
        for args in (("show",), ("get", "review", "missing"), ("sessions",), ("reviews",)):
            self.assertEqual(self.call(*args)["status"], "not_initialized")
        self.assertFalse(self.directory.exists())

    def test_review_schedule_records_real_results_and_intervals(self):
        self.save({"review_items": [item()]})
        on = date(2026, 10, 16)
        for attempts, interval in enumerate((1, 3, 7, 14, 14), start=1):
            self.save({"review_results": [result(on=on.isoformat())]})
            review = self.call("get", "review", "repeat")["item"]
            self.assertEqual(review["attempts"], attempts)
            self.assertEqual(review["interval_days"], interval)
            self.assertEqual(review["last_reviewed_on"], on.isoformat())
            self.assertEqual(review["last_mode"], "text")
            self.assertIn("no prompt", review["last_evidence"])
            self.assertEqual(review["next_review"], (on + timedelta(days=interval)).isoformat())
            on = date.fromisoformat(review["next_review"])

    def test_prompt_or_failure_resets_interval(self):
        self.save({"review_items": [item()]})
        self.save({"review_results": [result()]})
        self.save({"review_results": [result(on="2026-10-17")]})
        self.assertEqual(self.read()["review_items"]["repeat"]["interval_days"], 3)
        for outcome in ("需要提示", "需要重练"):
            self.save({"review_results": [result(on="2026-10-20", outcome=outcome)]})
            review = self.read()["review_items"]["repeat"]
            self.assertEqual(review["interval_days"], 1)
            self.assertEqual(review["next_review"], "2026-10-21")

    def test_same_day_success_does_not_advance_interval(self):
        self.save({"review_items": [item()], "review_results": [result()]})
        self.save({"review_results": [result()]})
        review = self.read()["review_items"]["repeat"]
        self.assertEqual(review["attempts"], 2)
        self.assertEqual(review["interval_days"], 1)

    def test_review_results_reject_invalid_or_duplicate_attempts(self):
        self.save({"review_items": [item()], "review_results": [result()]})
        invalid = [[result(), result()], [result(outcome="未评估")],
                   [result(on="2026-10-15")], [{**result(), "evidence": ""}],
                   [{**result(), "mode": "unknown"}], [result(on="2026-02-30")]]
        before = (self.directory / "progress.json").read_bytes()
        for results in invalid:
            with self.subTest(results=results):
                self.save({"review_results": results}, ok=False)
                self.assertEqual((self.directory / "progress.json").read_bytes(), before)

    def test_counts_cannot_be_changed_by_editing_item_metadata(self):
        self.save({"review_items": [item()]})
        for field, value in (("attempts", 10), ("last_result", "独立完成"), ("interval_days", 14)):
            self.save({"review_items": [{"id": "repeat", field: value}]}, ok=False)
        self.save({"review_items": [{"id": "repeat", "issue": "Corrected synthetic note"}]})
        self.assertEqual(self.read()["review_items"]["repeat"]["attempts"], 0)

    def test_explicit_rescheduling_keeps_metadata_consistent(self):
        self.save({"review_items": [item()], "review_results": [result()]})
        self.save({"review_items": [{"id": "repeat", "next_review": "2026-11-15"}]})
        self.assertEqual(self.read()["review_items"]["repeat"]["interval_days"], 30)
        self.save({"review_results": [result(on="2026-11-15")]})
        self.assertEqual(self.read()["review_items"]["repeat"]["interval_days"], 30)
        self.save({"review_items": [{"id": "repeat", "next_review": "2026-11-14"}]}, ok=False)

    def test_partial_scheduling_metadata_and_invalid_counters_are_rejected(self):
        self.save({"review_items": [item()]})
        healthy = self.read()
        for value in (True, -1, "3"):
            broken = copy.deepcopy(healthy)
            broken["review_items"]["repeat"]["attempts"] = value
            self.put(broken)
            self.call("show", ok=False)
        broken = copy.deepcopy(healthy)
        broken["review_items"]["repeat"]["last_reviewed_on"] = "2026-10-16"
        self.put(broken)
        self.call("show", ok=False)

    def test_updated_defaults_do_not_replace_an_existing_plan(self):
        self.assertEqual(self.read()["profile"]["daily_minutes"], 15)
        self.assertEqual(self.read()["profile"]["days_per_week"], 3)
        self.save({"profile": {"daily_minutes": 60, "days_per_week": 6, "plan_months": 4},
                   "session": session("existing")})
        before = (self.directory / "progress.json").read_bytes()
        self.call("init")
        self.call("show")
        self.assertEqual((self.directory / "progress.json").read_bytes(), before)
        self.save({"progress": {"notes": "Synthetic follow-up; keep learner plan"}})
        self.assertEqual(self.read()["profile"]["daily_minutes"], 60)
        self.assertEqual(self.read()["profile"]["days_per_week"], 6)
        self.assertEqual(self.read()["profile"]["plan_months"], 4)

    def test_installed_custom_path_and_generic_default_are_separate(self):
        skill = Path(self.temp.name) / "installed"
        (skill / "scripts").mkdir(parents=True)
        script = skill / "scripts/progress.py"
        shutil.copy2(SCRIPT, script)
        config = skill / "settings.json"
        custom = Path(self.temp.name) / "existing-learner-data"
        shutil.copytree(self.directory, custom)
        config.write_text(json.dumps({"data_dir": str(custom)}))
        before = {p.name: p.read_bytes() for p in custom.iterdir() if p.is_file()}
        response = subprocess.run([sys.executable, str(script), "init"], capture_output=True,
                                  text=True, env=self.env)
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertEqual(json.loads(response.stdout)["data_file"], str(custom / "progress.json"))
        self.assertEqual({p.name: p.read_bytes() for p in custom.iterdir() if p.is_file()}, before)
        home = Path(self.temp.name) / "new-home"
        home.mkdir()
        shutil.copy2(SCRIPT.parents[1] / "settings.json", config)
        response = subprocess.run([sys.executable, str(script), "show"], capture_output=True,
                                  text=True, env={**self.env, "HOME": str(home)})
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertEqual(json.loads(response.stdout)["data_file"],
                         str(home / ".local/share/travel-english-coach/progress.json"))
        self.assertEqual(json.loads(response.stdout)["status"], "not_initialized")
        self.assertFalse((home / ".local").exists())
        self.assertEqual({p.name: p.read_bytes() for p in custom.iterdir() if p.is_file()}, before)

    def test_large_archive_queries_are_read_only_and_checkpoint_writes_are_bounded(self):
        state = self.read()
        for n in range(2000):
            entry = {**session(str(n)), "minutes": None, "summary": "Synthetic fixture",
                     "next_step": "", "updated_at": state["updated_at"]}
            state["sessions"][str(n)] = entry
            state["review_items"][str(n)] = {**item(str(n), "2026-10-16"),
                                           "attempts": 0, "last_result": "未评估"}
        self.put(state)
        before = (self.directory / "progress.json").read_bytes()
        view = self.call("show", "--today", "2026-10-16", "--limit", 3)
        self.assertEqual(view["due_review_count"], 2000)
        self.assertEqual(len(view["due_review_items"]), 3)
        self.assertLess(len(json.dumps(view)), 8000)
        self.call("reviews", "--limit", 3)
        self.assertEqual((self.directory / "progress.json").read_bytes(), before)
        patch = self.patch_file({"session": {"id": "0", "summary": "Updated synthetic checkpoint"}})
        with mock.patch.object(sys, "argv", self.argv("save", "--file", patch,
                                                      "--expected-revision", state["revision"])[1:]), \
             mock.patch.object(progress, "atomic_json", wraps=progress.atomic_json) as writes:
            saved = progress.main()
        self.assertEqual(saved["session_count"], 2000)
        self.assertEqual(saved["review_item_count"], 2000)
        self.assertEqual([call.args[0].name for call in writes.call_args_list],
                         ["progress.previous.json", "progress.json"])
        self.assertEqual(json.loads((self.directory / "progress.previous.json").read_text()), state)
        self.assertEqual(self.read()["sessions"]["1999"], state["sessions"]["1999"])
        self.assertEqual(self.read()["review_items"], state["review_items"])

    def test_init_is_idempotent_and_does_not_reset_progress(self):
        self.save({"profile": {"daily_minutes": 30}, "session": session()})
        before = (self.directory / "progress.json").read_bytes()
        self.call("init")
        self.assertEqual((self.directory / "progress.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
