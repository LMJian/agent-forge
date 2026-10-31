"""Observable collector safety, coverage and history behavior in disposable inputs."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "skills/brownfield-recon/scripts/collect_evidence.py"
spec = importlib.util.spec_from_file_location("recon_collector", SCRIPT)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="recon-inputs-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def search(self, keyword, **kwargs):
        warnings, searches = [], {}
        files = collector.list_files(self.root, warnings)
        hits = collector.keyword_hits(self.root, [keyword], kwargs.pop("max_hits", 10), warnings,
                                      files=files, searches=searches, **kwargs)
        return hits[keyword], searches[keyword], warnings

    def test_ignored_credentials_never_reach_content_search(self):
        private = ["secrets.yaml", "secrets.ppe.json", ".netrc", ".npmrc", ".pypirc",
                   "service-account.json", ".env.local", "keys/key.pem", ".aws/config"]
        for name in private:
            self.write(name, "FIXTURE_SECRET_SENTINEL\n")
        self.write(".gitignore", "\n".join(private))
        self.write("app.py", "FIXTURE_PUBLIC_SENTINEL\n")
        commands = []
        original = collector.run

        def spy(cmd, *args, **kwargs):
            if "--json" in cmd:
                commands.extend(cmd[cmd.index("--") + 2:])
            return original(cmd, *args, **kwargs)

        with patch.object(collector, "run", side_effect=spy):
            hits, result, _ = self.search("FIXTURE_SECRET_SENTINEL")
        self.assertFalse(set(commands).intersection(private))
        self.assertFalse(hits)
        self.assertTrue(result["complete"])
        self.assertTrue(self.search("FIXTURE_PUBLIC_SENTINEL")[0])

    def test_snippets_redact_assignments_headers_and_url_credentials(self):
        self.write("app.py", 'client_secret = "FAKE_SECRET_VALUE"\n'
                   'app_secret = "FAKE_APP_SECRET"\nsecret = "FAKE_BARE_SECRET"\n'
                   'headers = {"Authorization": "Bearer FAKE_BEARER_VALUE"}\n'
                   'endpoint = "https://fixture:FAKE_URL_PASSWORD@example.invalid/"\n')
        for keyword, value in [("client_secret", "FAKE_SECRET_VALUE"),
                               ("app_secret", "FAKE_APP_SECRET"), ("secret", "FAKE_BARE_SECRET"),
                               ("Authorization", "FAKE_BEARER_VALUE"), ("endpoint", "FAKE_URL_PASSWORD")]:
            hits, result, _ = self.search(keyword)
            self.assertTrue(hits)
            self.assertTrue(result["complete"])
            self.assertNotIn(value, json.dumps(hits))
            self.assertIn("REDACTED", json.dumps(hits))

    def test_error_is_not_a_complete_negative_result(self):
        self.write("app.py", "hello\n")
        hits, result, _ = self.search("[", fixed=False)
        self.assertFalse(hits)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_kind"], "command_error")
        self.assertFalse(result["complete"])
        self.assertEqual(self.search("absent")[1]["status"], "no_match")

    def test_missing_tool_has_explicit_outcome(self):
        with patch.object(collector.shutil, "which", return_value=None):
            hits, result, _ = self.search("absent")
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["complete"])

    def test_malformed_and_non_text_events_cannot_be_complete_no_match(self):
        self.write("app.py", "hello\n")
        files = ["app.py"]
        for stdout, expected in [('[]\n', "error"), ('not-json\n', "error"),
                                 (json.dumps({"type": "match", "data": {"path": {"bytes": "YQ=="},
                                     "lines": {"text": "MATCH"}, "line_number": 1}}) + '\n', "partial")]:
            searches = {}
            with patch.object(collector, "run", return_value=(0, stdout, "")):
                collector.keyword_hits(self.root, ["MATCH"], 1, [], files=files, searches=searches)
            self.assertEqual(searches["MATCH"]["status"], expected)
            self.assertFalse(searches["MATCH"]["complete"])

    def test_byte_budget_bounds_raw_capture_and_reports_incomplete(self):
        self.write("long.txt", "MATCH " + "x" * 262144)
        hits, result, _ = self.search("MATCH", max_hits=1, byte_budget=4096)
        self.assertLessEqual(result["output_bytes"], 4096)
        self.assertIn("byte_budget", result["reason_codes"])
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["complete"])

    def test_command_budget_stops_child_and_retains_bounded_output(self):
        rc, out, _ = collector.run([sys.executable, "-c", "import os; os.write(1, b'x' * 2000000)"],
                                    self.root, max_output_bytes=1024)
        self.assertEqual(rc, 125)
        self.assertEqual(len(out), 1024)

    def test_timeout_is_not_empty_success(self):
        rc, _, _ = collector.run([sys.executable, "-c", "import time; time.sleep(2)"], self.root, timeout=0.03)
        self.assertEqual(rc, 124)

    def test_sample_limit_and_exact_match_have_different_coverage(self):
        self.write("app.py", "MATCH\nMATCH\nMATCH\n")
        _, result, _ = self.search("MATCH", max_hits=1)
        self.assertFalse(result["complete"])
        self.assertIn("hit_limit", result["reason_codes"])
        self.write("app.py", "MATCH\n")
        _, result, _ = self.search("MATCH", max_hits=1)
        self.assertEqual(result["status"], "matched")
        self.assertTrue(result["complete"])

    def test_skipped_oversized_input_prevents_absence_claim(self):
        self.write("large.txt", "x" * ((2 << 20) + 1))
        _, result, _ = self.search("absent")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["skipped_files"]["oversized"], 1)

    def test_symlink_sources_and_scopes_are_not_followed(self):
        self.write("app.py", "MATCH\n")
        (self.root / "link.py").symlink_to(self.root / "app.py")
        hits, _, _ = self.search("MATCH")
        self.assertEqual([h["path"] for h in hits], ["app.py"])
        with self.assertRaisesRegex(ValueError, "symlink"):
            collector.normalize_scopes(self.root, ["link.py"])

    def test_diverged_base_does_not_pollute_branch_hotspots(self):
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

        def git(*args):
            return subprocess.run(["git", *args], cwd=self.root, env=env, check=True,
                                  capture_output=True, text=True).stdout.strip()

        def commit(message):
            git("add", ".")
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "-c", "commit.gpgsign=false", "commit", "-qm", message)

        git("init", "-qb", "main")
        self.write("base.py", "base=1\n")
        commit("common")
        git("checkout", "-qb", "topic")
        self.write("topic.py", "topic=1\n")
        commit("topic change")
        git("checkout", "-q", "main")
        self.write("base_only.py", "base_only=1\n")
        commit("base advancement")
        git("checkout", "-q", "topic")
        evidence = collector.git_evidence(self.root, "main", 40, 80, [])
        self.assertEqual([r["path"] for r in evidence["branch_diff_files"]], ["topic.py"])
        self.assertEqual([r["path"] for r in evidence["history_hotspots"]], ["topic.py"])
        self.assertEqual(evidence["churn_range"], evidence["merge_base_commit"] + "..HEAD")

    def test_cli_preserves_legacy_hits_with_structured_outcomes(self):
        self.write("app.py", "MATCH\n")
        result = subprocess.run([sys.executable, str(SCRIPT), "--repo-root", str(self.root),
                                 "--keyword", "MATCH", "--regex-keyword", "[", "--output", "-"],
                                capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        self.assertEqual(data["schema_version"], "brownfield-recon-evidence-v1")
        self.assertTrue(data["keyword_hits"]["MATCH"])
        self.assertEqual(data["searches"]["fixed"]["MATCH"]["status"], "matched")
        self.assertEqual(data["searches"]["regex"]["["]["status"], "error")

    def test_cli_rejects_non_finite_or_non_positive_budgets(self):
        for option, value in [("--search-timeout", "nan"), ("--search-timeout", "inf"),
                              ("--search-byte-budget", "0")]:
            result = subprocess.run([sys.executable, str(SCRIPT), "--repo-root", str(self.root),
                                     option, value], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
