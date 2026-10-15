"""Validate both distributable source and Codex's versioned installation layout."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("distribution_validator", ROOT / "scripts/validate_distribution.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="harness-distribution-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "harness-devflow" / "1.0.0+codex.fixture"
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns("__pycache__", ".git", ".harness", ".DS_Store"))
        self.manifest = self.root / ".codex-plugin/plugin.json"
        data = json.loads(self.manifest.read_text())
        data["version"] = self.root.name
        self.manifest.write_text(json.dumps(data))

    def test_codex_cache_accepts_matching_base_version_and_build_suffix(self):
        self.assertEqual(validator.validate(self.root), [])

    def test_wrong_plugin_directory_is_rejected(self):
        wrong = self.root.with_name("unrelated-directory")
        self.root.rename(wrong)
        self.assertTrue(any("cache layout" in e for e in validator.validate(wrong)))

    def test_mismatched_host_base_versions_are_rejected(self):
        path = self.root / ".claude-plugin/plugin.json"
        data = json.loads(path.read_text())
        data["version"] = "2.0.0"
        path.write_text(json.dumps(data))
        self.assertTrue(any("base version" in e for e in validator.validate(self.root)))
