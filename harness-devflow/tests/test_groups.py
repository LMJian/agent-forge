"""Two independent Git repositories, dependency pins and real integration receipts."""
from pathlib import Path
import shutil

from harness import groups, runner
from harness import git as vcs
from harness.engine import Workflow
from harness.model import HarnessError
from harness.storage import atomic_json, read_json
from test_workflow import RepoCase


class RepositoryGroupTests(RepoCase):
    def setUp(self):
        super().setUp()
        self.flow.abort("Use independent review tasks for this coordination fixture")
        config = read_json(self.root / ".harness/project.json")
        config["workflow"] = {}
        atomic_json(self.root / ".harness/project.json", config)
        self.commit("Configure shared integration fixture")
        self.protocol = self.root.parent / (self.root.name + "-protocol")
        self.addCleanup(shutil.rmtree, self.protocol, True)
        self.git("clone", "--no-hardlinks", str(self.root), str(self.protocol))
        self.git("config", "user.email", "fixture@example.test", root=self.protocol)
        self.git("config", "user.name", "Fixture", root=self.protocol)
        protocol_sha = vcs.head(self.protocol)
        self.write("protocol.version", protocol_sha + "\n")
        self.commit("Pin protocol dependency")
        options = {"entry": "review", "profile": "light"}
        self.flow = Workflow(self.root, "service")
        self.flow.start("Review consumer", "main", options=options, acceptance=["Preserve base value"])
        self.other = Workflow(self.protocol, "protocol")
        self.other.start("Review protocol", "HEAD", options={**options, "stages": {"integration": False}},
                         acceptance=["Preserve base value"])
        self.manifest = self.root / ".harness/runs/service/group-input.json"
        atomic_json(self.manifest, {"schema_version": 1, "id": "location", "goal": "Verify protocol and service together",
            "repositories": [
                {"id": "protocol", "path": str(self.protocol), "task": "protocol", "revision": protocol_sha},
                {"id": "service", "path": str(self.root), "task": "service", "revision": vcs.head(self.root), "depends_on": ["protocol"]}],
            "contracts": [{"producer": "protocol", "consumer": "service", "path": "protocol.version", "expected": protocol_sha}],
            "integration": {"repository": "service", "check": "unit"}})

    def verify(self, flow, stage, *, complete=True):
        flow.enter(stage)
        receipt = runner.run(flow, "check", "unit")
        self.assertEqual(receipt["status"], "passed", receipt)
        if complete:
            artifact = flow.directory / "artifacts" / (stage + ".md")
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("Checked the value contract in both fixtures.\n")
            report = artifact.with_suffix(".json")
            atomic_json(report, {"schema_version": 2, "stage": stage, "status": "pass", "summary": "Checked contract",
                                 "findings": [], "artifacts": [str(artifact)], "checks": [receipt["id"]]})
            flow.complete(stage, str(report))
        return receipt

    def test_group_requires_matching_dependency_and_a_new_shared_check(self):
        linked = groups.link(self.root, str(self.manifest))
        self.assertEqual(linked["waves"], [["protocol"], ["service"]])
        self.assertEqual(linked["status"], "awaiting_integration")
        self.verify(self.other, "review")
        self.verify(self.flow, "review")
        receipt = self.verify(self.flow, "integration")
        result = groups.record(self.root, "location", "service", receipt["id"])
        self.assertEqual(result["status"], "verified", result)
        self.assertEqual(len(result["shared_checks"]), 1)
        self.git("commit", "--allow-empty", "-m", "New protocol revision", root=self.protocol)
        stale = groups.status(self.root, "location")
        self.assertEqual(stale["status"], "stale")
        self.assertIn("Pinned revision", str(stale["problems"]))

    def test_preexisting_check_cannot_claim_it_tested_new_group(self):
        self.verify(self.other, "review")
        self.verify(self.flow, "review")
        old = self.verify(self.flow, "integration", complete=False)
        groups.link(self.root, str(self.manifest))
        with self.assertRaisesRegex(HarnessError, "after linking"):
            groups.record(self.root, "location", "service", old["id"])
        new = self.verify(self.flow, "integration", complete=False)
        self.assertEqual(groups.record(self.root, "location", "service", new["id"])["status"], "in_progress")

    def test_dependency_mismatch_and_tampered_log_do_not_verify(self):
        groups.link(self.root, str(self.manifest))
        self.verify(self.other, "review")
        self.verify(self.flow, "review")
        receipt = self.verify(self.flow, "integration")
        groups.record(self.root, "location", "service", receipt["id"])
        self.write("protocol.version", "wrong-version\n")
        self.assertIn("Expected dependency", str(groups.status(self.root, "location")["problems"]))
        self.git("restore", "protocol.version")
        Path(receipt["stderr"]).write_text("modified evidence")
        self.assertEqual(groups.status(self.root, "location")["status"], "stale")

    def test_dependency_cycle_or_same_repository_cannot_be_linked(self):
        manifest = read_json(self.manifest)
        manifest["repositories"][0]["depends_on"] = ["service"]
        atomic_json(self.manifest, manifest)
        with self.assertRaisesRegex(HarnessError, "cycle"):
            groups.link(self.root, str(self.manifest))
        manifest["repositories"][0]["depends_on"] = []
        manifest["repositories"][0].update(path=str(self.root), task="service", revision=vcs.head(self.root))
        atomic_json(self.manifest, manifest)
        with self.assertRaisesRegex(HarnessError, "same Git"):
            groups.link(self.root, str(self.manifest))
