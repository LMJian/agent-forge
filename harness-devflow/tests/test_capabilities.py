"""Portable providers, real recon collection, report handoff and evidence invalidation."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

from harness import capabilities, runner
from harness.cli import main
from harness.model import HarnessError, digest
from harness.storage import atomic_json, read_json
from test_workflow import RepoCase


class CapabilityTests(RepoCase):
    def intake(self, modules=None):
        return self.finish("intake", details={"acceptance": ["AC-1"], "modules": modules or [
            {"id": "core", "acceptance": ["AC-1"]}]})

    def result(self, use, *, status="pass", details=None, findings=None, tool_runs=None):
        self.counter += 1
        directory = Path(use["output_directory"])
        artifact = directory / f"result-{self.counter}.md"
        artifact.write_text("# Observed baseline or proposed design\nThe existing value returns 1; the requested result is 2.\n")
        report = directory / f"result-{self.counter}.json"
        data = {"schema_version": 2, "capability_id": use["id"], "slot": use["slot"], "status": status,
                "summary": "Investigated the fixture and documented the actual next-step evidence",
                "artifacts": [str(artifact)], "details": details or {}, "findings": findings or [],
                "tool_runs": tool_runs or []}
        atomic_json(report, data)
        return report

    def recon(self):
        self.flow.enter("intake")
        return capabilities.prepare(self.flow, "recon", "Establish old return-value behavior")

    def test_recon_uses_bundled_copy_and_is_idempotent(self):
        with patch.object(Path, "home", side_effect=AssertionError("No home-directory discovery")):
            use = self.recon()
            again = capabilities.prepare(self.flow, "recon", "Reuse the same prepared investigation")
        self.assertEqual(use["provider"], "brownfield-recon")
        self.assertEqual(use["id"], again["id"])
        self.assertTrue(Path(use["skill_path"]).is_relative_to(self.flow.directory))
        self.assertTrue((Path(use["skill_path"]).parent / "scripts/collect_evidence.py").is_file())

    def test_real_collector_runs_without_scanning_runtime_or_secret_files(self):
        self.write(".env.local", "SUPER_SECRET_FIXTURE=do-not-collect\n")
        self.write("link.py", "not used\n")
        (self.root / "link.py").unlink()
        (self.root / "link.py").symlink_to(self.root / "base.py")
        self.write("secrets.yaml", "SUPER_SECRET_FIXTURE=do-not-collect\n")
        use = self.recon()
        receipt = runner.run(self.flow, "capability", "recon", scopes=["."], keywords=["value", "SUPER_SECRET_FIXTURE"])
        self.assertEqual(receipt["status"], "passed", receipt)
        data = read_json(Path(receipt["stdout"]))
        self.assertEqual(data["schema_version"], "brownfield-recon-evidence-v1")
        self.assertIn(".harness", data["safety"]["skipped_directories"])
        self.assertNotIn("do-not-collect", json.dumps(data))
        self.assertEqual(data["keyword_hits"]["SUPER_SECRET_FIXTURE"], [])
        self.assertEqual(data["parameters"]["base_ref"], use["head"])
        path = self.result(use, details={"phase": "design", "readiness": "READY_WITH_GAPS"}, tool_runs=[receipt["id"]])
        capabilities.complete(self.flow, "recon", str(path))
        self.assertEqual(self.intake()["current_stage"], "design")
        self.assertIn(str(Path(receipt["stdout"]).relative_to(self.root)), [e["path"] for e in self.flow.load()["stages"]["intake"]["evidence"]])

    def test_collector_direct_harness_output_and_no_overwrite(self):
        script = capabilities.PLUGIN_ROOT / "skills/brownfield-recon/scripts/collect_evidence.py"
        path = self.flow.directory / "artifacts/baseline.json"
        argv = [sys.executable, str(script), "--repo-root", str(self.root), "--scope", "base.py", "--output", str(path)]
        result = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(path.is_file())
        second = subprocess.run(argv, capture_output=True, text=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("already exists", second.stderr)
        invalid = subprocess.run([*argv[:-1], str(self.flow.path)], capture_output=True, text=True)
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("output inside", invalid.stderr)

    def test_backend_uses_server_design_and_other_domains_remain_generic(self):
        self.flow.configure_flow({"domain": "backend"}, "Backend service feature")
        self.intake()
        self.flow.enter("design")
        use = capabilities.prepare(self.flow, "design", "Specify service behavior")
        self.assertEqual(use["provider"], "server-tech-design")
        request = read_json(Path(use["request"]))
        self.assertEqual(request["operation"], "draft")
        self.assertEqual(request["format"], "local_markdown")
        self.assertTrue(request["input_reports"])
        self.flow.configure_flow({"domain": "frontend"}, "The requested scope is frontend-only")
        self.flow.enter("design")
        other = capabilities.prepare(self.flow, "design", "Use the generic frontend design method")
        self.assertEqual(other["provider"], "builtin")
        self.assertNotEqual(use["id"], other["id"])

    def test_shared_professional_design_maps_multiple_modules(self):
        self.flow.configure_flow({"domain": "backend"}, "Two related backend modules")
        modules = [{"id": "one", "acceptance": ["AC-1"]}, {"id": "two", "acceptance": ["AC-1"]}]
        self.intake(modules)
        self.flow.enter("design")
        use = capabilities.prepare(self.flow, "design", "Describe the complete cross-module flow")
        path = self.result(use)
        capabilities.complete(self.flow, "design", str(path))
        document = read_json(path)["artifacts"][0]
        result = self.flow.complete("design", str(self.report("design", artifacts=[document], details={"designs": {"one": document, "two": document}})))
        self.assertEqual(result["current_stage"], "design_audit")
        evidence = self.flow.load()["stages"]["design"]["evidence"]
        self.assertIn(str(Path(use["skill_path"]).relative_to(self.root)), [e["path"] for e in evidence])

    def test_prepared_or_blocked_recon_cannot_advance_intake(self):
        use = self.recon()
        with self.assertRaisesRegex(HarnessError, "not complete"):
            self.intake()
        path = self.result(use, status="blocked", details={"phase": "design", "readiness": "BLOCKED"})
        capabilities.complete(self.flow, "recon", str(path))
        with self.assertRaisesRegex(HarnessError, "not complete"):
            self.intake()
        fixed = self.result(use, details={"phase": "design", "readiness": "READY"})
        done = capabilities.complete(self.flow, "recon", str(fixed))
        self.assertEqual(len(done["history"]), 1)
        self.assertEqual(self.intake()["current_stage"], "design")

    def test_wrong_phase_or_fabricated_collector_receipt_is_rejected(self):
        use = self.recon()
        with self.assertRaisesRegex(HarnessError, "next phase"):
            capabilities.complete(self.flow, "recon", str(self.result(use, details={"phase": "release", "readiness": "READY"})))
        with self.assertRaisesRegex(HarnessError, "Collector receipt"):
            capabilities.complete(self.flow, "recon", str(self.result(use, details={"phase": "design", "readiness": "READY"}, tool_runs=["invented"])))

    def test_baseline_cannot_be_completed_after_code_changes(self):
        use = self.recon()
        self.write("base.py", "def value():\n    return 2\n")
        with self.assertRaisesRegex(HarnessError, "Code changed"):
            capabilities.complete(self.flow, "recon", str(self.result(use, details={"phase": "design", "readiness": "READY"})))

    def test_scoped_recon_survives_unrelated_changes_and_head_movement(self):
        use = self.recon()
        self.write("unrelated.py", "unrelated = True\n")
        self.commit("Unrelated source change")
        receipt = runner.run(self.flow, "capability", "recon", scopes=["base.py"], keywords=["value"])
        self.assertEqual(receipt["status"], "passed")
        path = self.result(use, details={"phase": "design", "readiness": "READY",
                                        "evidence_paths": ["base.py", "tests"]}, tool_runs=[receipt["id"]])
        done = capabilities.complete(self.flow, "recon", str(path))
        self.assertEqual(done["recon_scopes"], ["base.py", "tests"])
        self.assertEqual(self.intake()["current_stage"], "design")

    def test_direct_inspection_can_declare_scope_without_collector(self):
        use = self.recon()
        self.write("unrelated.py", "unrelated = True\n")
        done = capabilities.complete(self.flow, "recon", str(self.result(use, details={
            "phase": "design", "readiness": "READY", "evidence_paths": ["base.py"]})))
        self.assertEqual(done["recon_scopes"], ["base.py"])

    def test_metadata_only_commit_does_not_invalidate_default_recon(self):
        use = self.recon()
        self.git("commit", "--allow-empty", "-m", "Metadata only")
        done = capabilities.complete(self.flow, "recon", str(self.result(use, details={
            "phase": "design", "readiness": "READY"})))
        self.assertEqual(done["recon_scopes"], ["."])

    def test_scope_cannot_hide_an_earlier_collected_dependency(self):
        use = self.recon()
        runner.run(self.flow, "capability", "recon", scopes=["base.py", "tests"], keywords=["value"])
        self.write("tests/test_base.py", "changed = True\n")
        with self.assertRaisesRegex(HarnessError, "Code changed"):
            capabilities.complete(self.flow, "recon", str(self.result(use, details={
                "phase": "design", "readiness": "READY", "evidence_paths": ["base.py"]})))

    def test_new_file_in_directory_scope_invalidates_recon(self):
        use = self.recon()
        runner.run(self.flow, "capability", "recon", scopes=["tests"], keywords=["value"])
        self.write("tests/new_dependency.py", "new_contract = True\n")
        with self.assertRaisesRegex(HarnessError, "Code changed"):
            capabilities.complete(self.flow, "recon", str(self.result(use, details={"phase": "design", "readiness": "READY"})))

    def test_deleted_input_and_changes_before_stage_handoff_are_rejected(self):
        use = self.recon()
        capabilities.complete(self.flow, "recon", str(self.result(use, details={
            "phase": "design", "readiness": "READY", "evidence_paths": ["base.py"]})))
        (self.root / "base.py").unlink()
        with self.assertRaisesRegex(HarnessError, "Code changed"):
            self.intake()

    def test_scope_paths_are_validated(self):
        use = self.recon()
        for paths in ["base.py", ["../outside"], [str(self.root / "base.py")], ["not-a-source-input"]]:
            with self.assertRaises(HarnessError):
                capabilities.complete(self.flow, "recon", str(self.result(use, details={
                    "phase": "design", "readiness": "READY", "evidence_paths": paths})))

    def test_explicit_missing_provider_does_not_fall_back_or_skip(self):
        self.flow.configure_flow({"capabilities": {"recon": "missing-method"}}, "Use the explicitly requested method")
        self.flow.enter("intake")
        with self.assertRaisesRegex(HarnessError, "Required capability"):
            capabilities.prepare(self.flow, "recon", "Use the requested method")
        with self.assertRaisesRegex(HarnessError, "Explicit capability"):
            self.intake()

    def test_custom_provider_is_loaded_from_project_relative_location(self):
        self.write(".harness/skills/project-recon/SKILL.md", "---\nname: project-recon\ndescription: Inspect project contracts.\n---\nRead the project schema.\n")
        self.flow.configure_flow({"capabilities": {"recon": "project-recon"}}, "Apply the project's investigation method")
        use = self.recon()
        self.assertEqual(use["provider"], "project-recon")
        self.assertTrue(use["source_path"].startswith(str(self.root)))

    def test_builtin_method_needs_only_the_existing_stage_report(self):
        self.intake()
        self.flow.enter("design")
        use = capabilities.prepare(self.flow, "design", "Generic tool design")
        self.assertEqual(use["provider"], "builtin")
        path = self.report("design")
        data = read_json(path)
        data["details"] = {"designs": {"core": data["artifacts"][0]}}
        atomic_json(path, data)
        self.flow.complete("design", str(path))
        self.assertEqual(self.flow.load()["capability_uses"][-1]["completion_source"], "stage_report")

    def test_audit_is_a_separate_review_invocation_and_findings_must_be_incorporated(self):
        self.to_approval()
        self.flow.reopen("design_audit", "Perform project-specific review")
        self.flow.configure_flow({"capabilities": {"design_audit": "server-tech-design"}}, "Use the bundled design reviewer")
        self.flow.enter("design_audit")
        use = capabilities.prepare(self.flow, "design_audit", "Review the completed design")
        self.assertEqual(read_json(Path(use["request"]))["operation"], "review")
        findings = [{"severity": "warning", "message": "Capacity estimate still needs load verification"}]
        capabilities.complete(self.flow, "design_audit", str(self.result(use, findings=findings)))
        with self.assertRaisesRegex(HarnessError, "incorporate"):
            self.flow.complete("design_audit", str(self.report("design_audit")))
        self.flow.complete("design_audit", str(self.report("design_audit", findings=findings)))

    def test_provider_snapshot_survives_source_move_and_detects_snapshot_tampering(self):
        portable = self.flow.directory / "portable-plugin"
        shutil.copytree(capabilities.PLUGIN_ROOT / "skills/brownfield-recon", portable / "skills/brownfield-recon")
        with patch.object(capabilities, "PLUGIN_ROOT", portable):
            use = self.recon()
        shutil.rmtree(portable)
        self.assertEqual(capabilities.prepare(self.flow, "recon", "Resume pinned provider")["id"], use["id"])
        Path(use["skill_path"]).write_text("changed source snapshot")
        with self.assertRaisesRegex(HarnessError, "Artifact changed"):
            capabilities.complete(self.flow, "recon", str(self.result(use, details={"phase": "design", "readiness": "READY"})))

    def test_changed_capability_output_invalidates_completed_stage(self):
        use = self.recon()
        path = self.result(use, details={"phase": "design", "readiness": "READY"})
        capabilities.complete(self.flow, "recon", str(path))
        self.intake()
        Path(read_json(path)["artifacts"][0]).write_text("Changed baseline")
        self.assertEqual(self.flow.status()["status"], "stale")

    def test_cli_capability_override_and_prepare(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--repo", str(self.root), "--task", "example", "configure-flow", "--domain", "backend",
                         "--capability", "recon=brownfield-recon", "--reason", "Investigate backend contract"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["workflow"]["capabilities"]["recon"], "brownfield-recon")
        self.flow.enter("intake")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--repo", str(self.root), "--task", "example", "use-skill", "recon", "--reason", "Read existing code"])
        self.assertEqual(code, 0)
        self.assertTrue(Path(json.loads(out.getvalue())["skill_path"]).is_file())

    def test_incomplete_state_is_rejected_without_normalization(self):
        state = self.flow.load()
        state.pop("capability_uses")
        for section in (state["workflow"], state["config"]["workflow"]):
            section.pop("domain", None)
            section.pop("capabilities", None)
        state["config_hash"] = digest(state["config"])
        atomic_json(self.flow.path, state)
        before = self.flow.path.read_bytes()
        with self.assertRaisesRegex(HarnessError, "Incomplete task state"):
            self.flow.status()
        self.assertEqual(before, self.flow.path.read_bytes())

    def test_auto_missing_provider_falls_back_but_explicit_binding_does_not(self):
        isolated = self.flow.directory / "minimal-plugin"
        builtin = isolated / "skills/intake/SKILL.md"
        builtin.parent.mkdir(parents=True)
        shutil.copyfile(capabilities.PLUGIN_ROOT / "skills/intake/SKILL.md", builtin)
        with patch.object(capabilities, "PLUGIN_ROOT", isolated):
            use = self.recon()
            self.assertEqual(use["provider"], "builtin")
            self.assertIn("unavailable", use["selection_reason"])
            self.flow.configure_flow({"capabilities": {"recon": "brownfield-recon"}}, "Require the named skill")
            self.flow.enter("intake")
            with self.assertRaisesRegex(HarnessError, "Required capability"):
                capabilities.prepare(self.flow, "recon", "Follow the explicit selection")

    def test_professional_review_cannot_pass_a_blocker_or_reuse_results_after_fixes(self):
        self.write(".harness/skills/project-review/SKILL.md", "---\nname: project-review\ndescription: Review project behavior.\n---\nCheck changed behavior and report actual findings.\n")
        self.commit("Add project review method")
        self.flow.configure_flow({"capabilities": {"review": "project-review"}}, "Use a project reviewer")
        self.to_review()
        use = capabilities.prepare(self.flow, "review", "Review the integrated change")
        blocker = [{"severity": "blocker", "message": "The observed output is incorrect"}]
        with self.assertRaisesRegex(HarnessError, "blocker"):
            capabilities.complete(self.flow, "review", str(self.result(use, findings=blocker)))
        capabilities.complete(self.flow, "review", str(self.result(use)))
        self.write("fix.py", "fix = True\n")
        self.commit("Change code after professional review")
        check = runner.run(self.flow, "check", "unit")
        with self.assertRaisesRegex(HarnessError, "after capability review"):
            self.flow.complete("review", str(self.report("review", checks=[check["id"]])))

    def test_preparing_and_snapshotting_do_not_advance_the_stage(self):
        use = self.recon()
        state = self.flow.status()
        self.assertEqual(state["current_stage"], "intake")
        self.assertEqual(state["status"], "running")
        self.assertEqual(state["capabilities"][0]["status"], "prepared")
        self.assertEqual(use["status"], "prepared")
