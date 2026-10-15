"""Portable skill selection and evidence handoff; the agent, not this CLI, runs the skill."""
from __future__ import annotations

from pathlib import Path
import re
import shutil
import sys
import uuid

from . import git as vcs
from .model import (BUNDLED_CAPABILITIES, CAPABILITY_STAGES, HarnessError, digest,
                    nonempty, now, require, strings, REPORT_SCHEMA)
from .storage import file_lock, inside, read_json, snapshots, verify_snapshots, atomic_json


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
BUILTIN = {"recon": "intake", "design": "design", "design_audit": "design-audit", "review": "review"}


def selection(workflow, state: dict, slot: str) -> dict:
    require(slot in CAPABILITY_STAGES, "Unknown capability slot")
    requested = state["workflow"]["capabilities"][slot]
    provider = requested
    if requested == "auto":
        provider = ("brownfield-recon" if slot == "recon" else "server-tech-design"
                    if slot in {"design", "design_audit"} and state["workflow"]["domain"] == "backend"
                    else "builtin")
    if provider == "brownfield-recon":
        require(slot == "recon", "brownfield-recon supports the recon slot")
    if provider == "server-tech-design":
        require(slot in {"design", "design_audit"}, "server-tech-design supports design and design_audit")
    if provider == "builtin":
        path = PLUGIN_ROOT / "skills" / BUILTIN[slot] / "SKILL.md"
    elif provider in BUNDLED_CAPABILITIES:
        path = PLUGIN_ROOT / "skills" / provider / "SKILL.md"
    else:
        path = inside(workflow.root, f".harness/skills/{provider}/SKILL.md")
    reason = "Selected the configured provider" if requested != "auto" else "Selected by capability and project domain"
    if not path.is_file() and requested == "auto":
        reason = f"Automatic provider {provider} unavailable; using the built-in method"
        provider = "builtin"
        path = PLUGIN_ROOT / "skills" / BUILTIN[slot] / "SKILL.md"
    require(path.is_file(), f"Required capability {provider} is missing; install/copy it into the plugin or .harness/skills/{provider}/")
    expected = BUILTIN[slot] if provider == "builtin" else provider
    content = path.read_text(encoding="utf-8")
    parts = content.split("---", 2)
    frontmatter = parts[1] if content.startswith("---\n") and len(parts) == 3 else ""
    match = re.search(r"^name:\s*['\"]?([a-z0-9-]+)['\"]?\s*$", frontmatter, re.M)
    require(match and match.group(1) == expected, "Provider SKILL.md name does not match its configured logical name")
    return {"provider": provider, "requested": requested, "source_path": str(path.resolve()), "selection_reason": reason}


def source_files(path: Path, *, builtin: bool) -> list[Path]:
    files = [path]
    if not builtin:
        for folder in ("references", "scripts", "assets"):
            directory = path.parent / folder
            require(not directory.is_symlink(), "Capability resources must not be symlinked")
            for item in sorted(directory.rglob("*")):
                require(not item.is_symlink(), "Capability resources must not contain symlinks")
                if item.is_file() and "__pycache__" not in item.parts and item.suffix not in {".pyc", ".pyo"}:
                    files.append(item)
    require(len(files) <= 1000 and sum(p.stat().st_size for p in files) <= 32 * 1024 * 1024,
            "Capability package exceeds the bounded snapshot size")
    return files


def active_use(workflow, state: dict, slot: str) -> dict:
    from .engine import current
    require(slot in CAPABILITY_STAGES and current(state) == CAPABILITY_STAGES[slot], "Capability does not match the current stage")
    stage = state["stages"][CAPABILITY_STAGES[slot]]
    require(stage["status"] == "running", "Enter the current stage first")
    key = stage.get("capabilities", {}).get(slot)
    use = next((u for u in state.get("capability_uses", []) if u["id"] == key), None)
    require(use and use["epoch"] == stage["epoch"], "Prepare the capability first")
    verify_snapshots(workflow.root, use["source_evidence"])
    return use


def prepare(workflow, slot: str, reason: str) -> dict:
    from .engine import current, stage_order
    nonempty(reason, "reason (why this capability is needed)")
    with file_lock(workflow.lock_path):
        state = workflow.load()
        workflow.consistent(state)
        stage = CAPABILITY_STAGES.get(slot)
        require(stage and current(state) == stage and state["stages"][stage]["status"] == "running",
                "Enter the matching stage before preparing a capability")
        item = state["stages"][stage]
        if slot in item.get("capabilities", {}):
            return active_use(workflow, state, slot)
        selected = selection(workflow, state, slot)
        uid = uuid.uuid4().hex
        directory = inside(workflow.root, workflow.directory / "capabilities" / uid)
        output = inside(workflow.root, workflow.directory / "artifacts" / "capabilities" / uid)
        output.mkdir(parents=True)
        original = Path(selected["source_path"])
        copied = []
        for path in source_files(original, builtin=selected["provider"] == "builtin"):
            target = inside(workflow.root, directory / "source" / path.relative_to(original.parent))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            copied.append(str(target))
        phase = "design" if state["workflow"]["enabled"]["design"] else "implementation"
        from .context import references
        context = references(workflow, state)
        prior = [item["report"] for item in context]
        inputs = list(dict.fromkeys(name for item in context for name in item["artifacts"]))
        source_evidence = snapshots(workflow.root, copied)
        source_digest = digest([{ "path": str(Path(p).relative_to(directory / "source")), "sha256": e["sha256"]}
                                for p, e in zip(copied, source_evidence)])
        request = {"schema_version": 1, "capability_id": uid, "slot": slot, "stage": stage,
                   "operation": {"recon": "investigate", "design": "draft", "design_audit": "review", "review": "review_code"}[slot],
                   "goal": state["goal"], "domain": state["workflow"]["domain"], "repository": str(workflow.root),
                   "head": vcs.head(workflow.root), "base_sha": state["base_sha"], "input_reports": prior,
                   "input_artifacts": inputs,
                   "review_context": state.get("review_context"),
                   "readiness_phase": phase if slot == "recon" else None,
                   "output_directory": str(output), "format": "local_markdown",
                   "constraints": ["Use the requested local output directory; no implicit document publication or telemetry",
                                   "Keep current facts, target decisions and executed verification distinct",
                                   "Return findings/artifacts; the Harness stage wrapper owns state and report conversion",
                                   "Reuse referenced baselines and scenarios; investigate only changed or unresolved facts"]}
        request_path = directory / "request.json"
        atomic_json(request_path, request)
        use = {"id": uid, "slot": slot, "stage": stage, "epoch": item["epoch"], **selected,
               "reason": reason, "status": "prepared", "prepared_at": now(), "source_digest": source_digest,
               "skill_path": str(directory / "source" / "SKILL.md"), "request": str(request_path),
               "output_directory": str(output), "source_evidence": snapshots(workflow.root, [*copied, str(request_path)]),
               "fingerprint": vcs.fingerprint(workflow.root), "head": request["head"], "history": []}
        state.setdefault("capability_uses", []).append(use)
        item.setdefault("capabilities", {})[slot] = uid
        workflow.save(state, "capability_prepared", slot=slot, provider=use["provider"], source_digest=source_digest)
        return use


def complete(workflow, slot: str, source: str) -> dict:
    with file_lock(workflow.lock_path):
        state = workflow.load()
        workflow.consistent(state)
        use = active_use(workflow, state, slot)
        require(use["status"] in {"prepared", "blocked"}, "Capability result already recorded; reopen the stage for a new attempt")
        require(not any(r["status"] in {"running", "unresolved"} for r in state["runs"]), "A command is still running")
        report = read_json(inside(workflow.root, source))
        require(report.get("schema_version") == REPORT_SCHEMA and report.get("capability_id") == use["id"] and
                report.get("slot") == slot, "Capability report does not match the prepared invocation")
        require(report.get("status") in {"pass", "blocked"}, "Capability status must be pass or blocked")
        nonempty(report.get("summary"), "capability.summary")
        artifacts = strings(report.get("artifacts"), "capability.artifacts")
        findings = report.get("findings", [])
        require(isinstance(findings, list), "Capability findings must be an array")
        if slot in {"design_audit", "review"}:
            require("findings" in report, "Professional review needs an explicit findings array")
        for finding in findings:
            require(isinstance(finding, dict) and finding.get("severity") in {"blocker", "warning", "suggestion"}, "Invalid capability finding")
            nonempty(finding.get("message"), "finding.message")
            require(report["status"] != "pass" or finding["severity"] != "blocker" or finding.get("resolved") is True,
                    "Unresolved capability blocker cannot pass")
        if slot == "recon":
            details = report.get("details", {})
            require(isinstance(details, dict), "Recon details must be an object")
            request = read_json(Path(use["request"]))
            require(details.get("phase") == request["readiness_phase"], "Recon readiness must name the requested next phase")
            readiness = details.get("readiness")
            require(isinstance(readiness, str) and readiness in {"READY", "READY_WITH_GAPS", "BLOCKED"}, "Invalid recon readiness")
            require((readiness == "BLOCKED") == (report["status"] == "blocked"), "Readiness and capability status disagree")
            require(use["fingerprint"] == vcs.fingerprint(workflow.root), "Code changed during baseline investigation; reopen intake")
        for previous in use["history"]:
            verify_snapshots(workflow.root, previous["evidence"])
        if use.get("evidence"):
            verify_snapshots(workflow.root, use["evidence"])
            require(str(inside(workflow.root, source)) != use["report"], "Keep prior evidence; use a new result file")
            use["history"].append({"status": use["status"], "evidence": use["evidence"]})
        tool_ids = strings(report.get("tool_runs", []), "capability.tool_runs", empty=True)
        logs = []
        for rid in tool_ids:
            receipt = next((r for r in state["runs"] if r["id"] == rid), None)
            require(receipt and receipt.get("capability_id") == use["id"] and receipt["status"] == "passed",
                    "Collector receipt is missing, failed or belongs to another invocation")
            logs.append(receipt["stdout"])
        use.update(status="complete" if report["status"] == "pass" else "blocked", completed_at=now(),
                   report=str(inside(workflow.root, source)), result_fingerprint=vcs.fingerprint(workflow.root),
                   evidence=snapshots(workflow.root, [source, *artifacts, *logs]))
        workflow.save(state, "capability_completed", slot=slot, provider=use["provider"], status=use["status"])
        return use


def stage_evidence(workflow, state: dict, stage: str, report: dict) -> list[str]:
    evidence = []
    for slot, mapped in CAPABILITY_STAGES.items():
        if mapped != stage:
            continue
        uid = state["stages"][stage].get("capabilities", {}).get(slot)
        configured = state["workflow"]["capabilities"][slot]
        require(uid or configured in {"auto", "builtin"}, f"Explicit capability {configured} must be prepared and completed")
        if not uid:
            continue
        use = next(u for u in state["capability_uses"] if u["id"] == uid)
        builtin = use["provider"] == "builtin" and use["status"] == "prepared"
        require(builtin or use["status"] == "complete", f"Capability {slot} is not complete; resolve its findings before advancing")
        for entries in (use["source_evidence"], use.get("evidence", []), *(h["evidence"] for h in use["history"])):
            verify_snapshots(workflow.root, entries)
            evidence.extend(e["path"] for e in entries)
        if not builtin and stage in {"design_audit", "review"}:
            produced = read_json(Path(use["report"])).get("findings", [])
            incorporated = {(f["severity"], f["message"]) for f in report.get("findings", [])}
            require(all((f["severity"], f["message"]) in incorporated for f in produced),
                    "Stage report must incorporate the professional review findings")
        if stage == "review" and not builtin:
            require(use["result_fingerprint"] == vcs.fingerprint(workflow.root), "Code changed after capability review; reopen review")
    return evidence


def finish_builtin(workflow, state: dict, stage: str, source: str, report: dict) -> None:
    for uid in state["stages"][stage].get("capabilities", {}).values():
        use = next(u for u in state["capability_uses"] if u["id"] == uid)
        if use["provider"] == "builtin" and use["status"] == "prepared":
            use.update(status="complete", completed_at=now(), report=str(inside(workflow.root, source)),
                       result_fingerprint=vcs.fingerprint(workflow.root), completion_source="stage_report",
                       evidence=snapshots(workflow.root, [source, *report["artifacts"]]))


def collector_spec(workflow, state: dict, scopes: list[str], keywords: list[str]) -> tuple[dict, dict]:
    use = active_use(workflow, state, "recon")
    require(use["status"] == "prepared" and use["provider"] == "brownfield-recon", "Collector requires a prepared brownfield-recon capability")
    require(use["fingerprint"] == vcs.fingerprint(workflow.root), "Baseline code changed; reopen intake")
    strings(scopes, "scopes", empty=True)
    strings(keywords, "keywords", empty=True)
    script = inside(workflow.root, Path(use["skill_path"]).parent / "scripts/collect_evidence.py")
    require(script.is_file(), "The selected skill has no bundled collector")
    argv = [sys.executable, str(script), "--repo-root", str(workflow.root), "--base-ref", use["head"], "--output", "-"]
    for scope in scopes:
        argv.extend(["--scope", scope])
    for keyword in keywords:
        argv.extend(["--keyword", keyword])
    return {"argv": argv, "timeout_seconds": state["config"]["check_timeout_seconds"]}, use
