"""Exercise push destination verification against real, local bare repositories."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ADAPTER = Path(__file__).resolve().parents[1] / "adapters/git_push.py"


class PushDestinationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="push-destinations-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root / "work"
        self.work.mkdir()
        self.git("init")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("checkout", "-b", "feature/push")
        self.git("commit", "--allow-empty", "-m", "Initial")
        self.old = self.git("rev-parse", "HEAD")
        self.fetch = self.bare("fetch.git")
        self.git("remote", "add", "fixture", str(self.fetch))
        self.git("push", "fixture", "HEAD:refs/heads/feature/push")
        self.git("commit", "--allow-empty", "-m", "Reviewed")
        self.head = self.git("rev-parse", "HEAD")
        self.request = self.root / "request.json"
        self.request.write_text(json.dumps({"stage": "push", "branch": "feature/push",
                                           "head": self.head, "repository": str(self.work)}))

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.work, check=True,
                              capture_output=True, text=True).stdout.strip()

    def bare(self, name):
        path = self.root / name
        self.git("init", "--bare", str(path))
        self.git("config", "core.hooksPath", str(path / "hooks"), cwd=path)
        return path

    def push(self):
        return subprocess.run([sys.executable, str(ADAPTER), "--remote", "fixture"],
                              env={**os.environ, "HARNESS_REQUEST": str(self.request)},
                              capture_output=True, text=True)

    def assert_head(self, path, head):
        self.assertEqual(self.git("rev-parse", "refs/heads/feature/push", cwd=path), head)

    def test_separate_push_url_is_verified_instead_of_fetch_url(self):
        destination = self.bare("push.git")
        self.git("remote", "set-url", "--push", "fixture", str(destination))
        result = self.push()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["remote_head"], self.head)
        self.assert_head(destination, self.head)
        self.assert_head(self.fetch, self.old)

    def test_all_push_urls_receive_and_verify_the_reviewed_head(self):
        destinations = [self.bare("one.git"), self.bare("two.git")]
        for path in destinations:
            self.git("remote", "set-url", "--add", "--push", "fixture", str(path))
        result = self.push()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for path in destinations:
            self.assert_head(path, self.head)
        self.assert_head(self.fetch, self.old)

    def test_mismatch_at_second_push_url_fails_even_when_first_matches(self):
        first, second = self.bare("one.git"), self.bare("two.git")
        for path in (first, second):
            self.git("remote", "set-url", "--add", "--push", "fixture", str(path))
        hook = second / "hooks/post-receive"
        hook.write_text(f"#!/bin/sh\ngit update-ref refs/heads/feature/push {self.old}\n")
        hook.chmod(0o755)
        result = self.push()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("does not match", json.loads(result.stdout)["summary"])
        self.assert_head(first, self.head)
        self.assert_head(second, self.old)

    def test_push_instead_of_rewrite_is_resolved_before_verification(self):
        destination = self.bare("rewritten.git")
        self.git("config", f"url.{destination}.pushInsteadOf", str(self.fetch))
        result = self.push()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_head(destination, self.head)
        self.assert_head(self.fetch, self.old)
