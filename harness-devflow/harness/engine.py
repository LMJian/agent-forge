"""Persistent stage machine. Only this module writes workflow status."""
from __future__ import annotations

import copy
from pathlib import Path
import uuid

from . import git as vcs
from .model import (ADAPTER_STAGES, CODE_BOUND, GATES, OPTIONAL, STAGES, TERMINAL,
                    HarnessError, default_config, digest, identifier, module_waves,
                    nonempty, now, require, strings, validate_config, resolve_workflow, execution_hash,
                    CAPABILITY_STAGES, STATE_SCHEMA, REPORT_SCHEMA)
from .storage import (atomic_json, file_lock, inside, read_json, snapshots, verify_snapshots)


def init_project(root: Path, base_ref: str | None = None) -> dict:
    root = vcs.repo_root(root)
    path = inside(root, ".harness/project.json")
    with file_lock(inside(root, ".harness/init.lock")):
        if path.exists():
            config = validate_config(read_json(path))
            require(base_ref is None or base_ref == config["base_ref"],
                    "Existing configuration differs; edit project.json explicitly")
            return {"repository": str(root), "config": str(path), "created": False}
        config = default_config()
        config["base_ref"] = base_ref
        validate_config(config)
        ignore = inside(root, ".harness/.gitignore")
        existing = ignore.read_text() if ignore.exists() else ""
        additions = [line for line in ("runs/", "worktrees/", "knowledge/", "*.lock")
                     if line not in existing.splitlines()]
        if additions:
            ignore.parent.mkdir(parents=True, exist_ok=True)
            ignore.write_text(existing.rstrip() + "\n" + "\n".join(additions) + "\n")
        atomic_json(path, config)
    return {"repository": str(root), "config": str(path), "created": True,
            "next": "Configure real review/integration commands, then start a task"}


def current(state: dict) -> str | None:
    return next((s for s in stage_order(state) if state["stages"][s]["status"] not in TERMINAL), None)


def stage_order(state: dict) -> list[str]:
    return state["workflow"]["order"]


def policy_stage(state: dict, stage: str) -> dict:
    item = blank_stage()
    if not state["workflow"]["enabled"][stage]:
        item.update(status="skipped", excluded=True, reason="Not selected by this task's workflow", ended_at=now())
    return item


def human_gate(state: dict, stage: str, report: dict | None = None) -> bool:
    if stage == "knowledge":
        return state["workflow"]["knowledge_approval"] and (report or {}).get("details", {}).get("outcome") != "no_changes"
    return stage in {"design_approval", "release"}


def blank_stage() -> dict:
    return {"status": "pending", "attempt": 0, "epoch": uuid.uuid4().hex[:12]}


class Workflow:
    def __init__(self, root: Path, task: str):
        self.root = vcs.repo_root(root)
        self.task = identifier(task)
        self.directory = inside(self.root, f".harness/runs/{self.task}")
        self.path = inside(self.root, self.directory / "state.json")
        self.lock_path = inside(self.root, self.directory / "state.lock")

    @property
    def config(self) -> dict:
        return validate_config(read_json(inside(self.root, ".harness/project.json")))

    def load(self, *, active: bool = True, config_check: bool = True, branch_check: bool = True) -> dict:
        state = read_json(self.path)
        require(state.get("schema_version") == STATE_SCHEMA,
                "Unsupported task schema_version (expected 3); no automatic conversion")
        require({"capability_uses", "git_common_dir", "initial_fingerprint", "initial_dirty", "config", "workflow"} <= set(state),
                "Incomplete task state; required fields are missing")
        require(state.get("task") == self.task and state.get("repository") == str(self.root),
                "State belongs to a different task or repository")
        require(not branch_check or state.get("branch") == vcs.branch(self.root),
                f"Use the owning checkout on branch {state.get('branch')}")
        require(state["git_common_dir"] == vcs.common_dir(self.root), "Task Git repository identity changed")
        if active:
            require(not state.get("aborted"), "Workflow was aborted; start a new task ID")
        if config_check:
            require(state["config_hash"] == digest(self.config),
                    "Project configuration changed; run sync-config with a reason")
        return state

    def save(self, state: dict, action: str, **details) -> None:
        state["revision"] += 1
        state["updated_at"] = now()
        state["events"].append({"revision": state["revision"], "at": now(),
                                "action": action, **details})
        atomic_json(self.path, state)

    def start(self, goal: str, base_ref: str | None = None, *, options: dict | None = None,
              acceptance: list[str] | None = None) -> dict:
        nonempty(goal, "goal")
        config = self.config
        workflow = resolve_workflow(config, options)
        if workflow["entry"] == "review":
            strings(acceptance, "existing-change acceptance")
        else:
            require(acceptance is None, "Acceptance override is only for start-review")
        branch = vcs.branch(self.root)
        base = base_ref or config["base_ref"] or vcs.head(self.root)
        nonempty(base, "base_ref")
        require(not base.startswith("-"), "base_ref cannot start with '-' ")
        base_sha = vcs.git(self.root, "rev-parse", "--verify", f"{base}^{{commit}}")
        require(vcs.is_ancestor(self.root, base_sha), "Base must be an ancestor of the current branch")
        # Serialize discovery plus creation, including distinct task IDs on the same branch.
        with file_lock(inside(self.root, ".harness/runs/start.lock")):
            require(not self.path.exists(), f"Task {self.task} already exists; use status/next")
            runs = inside(self.root, ".harness/runs")
            for path in runs.glob("*/state.json"):
                other = read_json(inside(self.root, path))
                require(other.get("schema_version") == STATE_SCHEMA,
                        "Unsupported task state in .harness/runs; archive incompatible task data outside this directory")
                require(other.get("branch") != branch or other.get("aborted") or current(other) is None,
                        f"Branch already has an active task: {other.get('task')}")
            state = {"schema_version": STATE_SCHEMA, "task": self.task, "goal": goal,
                     "repository": str(self.root), "branch": branch, "base_ref": base,
                     "base_sha": base_sha, "start_head": vcs.head(self.root),
                     "git_common_dir": vcs.common_dir(self.root),
                     "initial_fingerprint": vcs.fingerprint(self.root), "initial_dirty": not vcs.clean(self.root),
                     "config": config, "config_hash": digest(config), "execution_hash": execution_hash(config), "revision": 0,
                     "created_at": now(), "aborted": False,
                     "workflow": workflow, "workflow_overrides": options or {}, "stages": {},
                     "runs": [], "capability_uses": [], "modules": {}, "waves": [], "wave_index": 0,
                     "history": [], "events": []}
            if workflow["entry"] == "review":
                state["review_context"] = {"acceptance": acceptance, "base_sha": base_sha,
                                           "scope": "base through HEAD plus staged, unstaged and untracked changes"}
            state["stages"] = {s: policy_stage(state, s) for s in workflow["order"]}
            self.save(state, "start", workflow=workflow)
        return self.summary(state)

    def stale(self, state: dict) -> list[dict]:
        problems = []
        code = None
        for stage in STAGES:
            item = state["stages"][stage]
            if item["status"] != "done":
                continue
            try:
                verify_snapshots(self.root, item.get("evidence", []))
                if stage in CODE_BOUND:
                    code = code or vcs.fingerprint(self.root)
                    require(item.get("fingerprint") == code, "Code changed after verification")
                if stage == "review":
                    from .reuse import validate_receipt
                    report = self.report_for(state, stage)
                    for receipt in state["runs"]:
                        if receipt["id"] in report.get("checks", []):
                            validate_receipt(self, state, receipt)
            except (HarnessError, ValueError, KeyError) as error:
                problems.append({"stage": stage, "reason": str(error)})
        return problems

    def consistent(self, state: dict) -> None:
        problems = self.stale(state)
        require(not problems, f"Evidence is stale; reopen {problems[0]['stage'] if problems else ''}: {problems}")

    def summary(self, state: dict) -> dict:
        from .hosts import resolve
        stage = current(state)
        problems = self.stale(state)
        try:
            if state["config_hash"] != digest(self.config):
                problems.append({"stage": "configuration", "reason": "Configuration changed; run sync-config with a reason"})
        except HarnessError as error:
            problems.append({"stage": "configuration", "reason": str(error)})
        return {"task": self.task, "branch": state["branch"], "revision": state["revision"],
                "workflow": state["workflow"],
                "execution": resolve(state["config"]["host"], state["workflow"]["assistance"]),
                "active_stages": [s for s in stage_order(state) if state["workflow"]["enabled"][s]],
                "current_stage": stage, "status": "aborted" if state["aborted"] else
                ("stale" if problems else (state["stages"][stage]["status"] if stage else "complete")),
                "stages": {s: item["status"] for s, item in state["stages"].items()},
                "stale": problems, "wave_index": state["wave_index"],
                "capabilities": [{k: u[k] for k in ("id", "slot", "stage", "epoch", "provider", "status", "source_digest", "request")}
                                 for u in state.get("capability_uses", [])
                                 if u["epoch"] == state["stages"][u["stage"]]["epoch"]],
                "waves": state["waves"], "modules": state["modules"],
                "state_file": str(self.path), "artifact_directory": str(self.directory / "artifacts")}

    def status(self) -> dict:
        with file_lock(self.lock_path):
            return self.summary(self.load(active=False, config_check=False))

    def bind_branch(self, reason: str) -> dict:
        """Attach a newly named host branch without changing the verified code identity."""
        nonempty(reason, "reason")
        with file_lock(inside(self.root, ".harness/runs/start.lock")), file_lock(self.lock_path):
            state = self.load(active=False, branch_check=False)
            require(state["branch"] is None and vcs.branch(self.root), "Only a detached task can bind a newly named branch")
            require(not any(r["status"] in {"running", "unresolved"} for r in state["runs"]), "Inspect active executions first")
            self.consistent(state)
            known = {state["initial_fingerprint"], *(s.get("fingerprint") for s in state["stages"].values())}
            known.update(m.get("fingerprint") for m in state["modules"].values())
            require(vcs.fingerprint(self.root) in known, "Record or verify current code before naming the branch")
            state["branch"] = vcs.branch(self.root)
            for module in state["modules"].values():
                if module.get("worktree") == str(self.root):
                    module["branch"] = state["branch"]
            self.assert_sole_active(state)
            self.save(state, "branch_bound", reason=reason, branch=state["branch"])
            return self.summary(state)

    def enter(self, stage: str) -> dict:
        with file_lock(self.lock_path):
            state = self.load()
            self.consistent(state)
            require(current(state) == stage, f"Expected stage {current(state)}, not {stage}")
            item = state["stages"][stage]
            if item["status"] == "running":
                return self.summary(state)
            require(item["status"] in {"pending", "failed"}, "Approval is pending; approve or revise")
            require(item["attempt"] < state["config"]["max_attempts"],
                    "Attempt limit reached; inspect failure and explicitly reopen with a reason")
            item.update(status="running", attempt=item["attempt"] + 1, started_at=now())
            self.save(state, "enter", stage=stage)
            return self.summary(state)

    def report_for(self, state: dict, stage: str) -> dict:
        return read_json(inside(self.root, state["stages"][stage]["report"]))

    def check_receipts(self, state: dict, report: dict, stage: str) -> None:
        names = state["config"]["stage_checks"].get(stage, [])
        require(bool(names), f"Configure at least one stage_checks.{stage} command; no checks ran")
        ids = strings(report.get("checks"), "report.checks")
        runs = {r["id"]: r for r in state["runs"]}
        found = set()
        code = vcs.fingerprint(self.root)
        for run_id in ids:
            require(run_id in runs, f"Unknown check receipt {run_id}")
            receipt = runs[run_id]
            require(receipt["kind"] == "check" and receipt["stage"] == stage and
                    receipt["epoch"] == state["stages"][stage]["epoch"] and
                    receipt["status"] == "passed" and receipt.get("module") is None,
                    f"Invalid or failed check receipt: {run_id}")
            require(receipt["fingerprint"] == code and receipt["config_hash"] == state["execution_hash"],
                    f"Stale check receipt: {run_id}")
            require(not any(r["kind"] == "check" and r["name"] == receipt["name"] and
                            r["stage"] == stage and r["epoch"] == receipt["epoch"] and
                            r.get("module") is None and r["status"] == "failed"
                            for r in state["runs"][state["runs"].index(receipt) + 1:]),
                    "A newer failed check supersedes the supplied receipt")
            verify_snapshots(self.root, receipt["evidence"])
            from .reuse import validate_receipt
            validate_receipt(self, state, receipt)
            found.add(receipt["name"])
        require(set(names) <= found, f"Missing required checks: {sorted(set(names) - found)}")

    def adapter_receipt(self, state: dict, report: dict, stage: str) -> dict:
        run_id = report.get("adapter_run")
        receipt = next((r for r in state["runs"] if r["id"] == run_id), None)
        require(receipt and receipt["kind"] == "adapter" and receipt["name"] == stage and
                receipt["epoch"] == state["stages"][stage]["epoch"] and receipt["status"] == "passed",
                f"A successful {stage} adapter receipt is required")
        require(receipt["config_hash"] == state["execution_hash"] and
                receipt["fingerprint"] == vcs.fingerprint(self.root), "Adapter receipt is stale")
        verify_snapshots(self.root, receipt["evidence"])
        response = receipt["response"]
        if stage == "monitor":
            require(response.get("state") == "merged", "PR is not merged; keep monitoring or handle closure")
        return receipt

    def validate_report(self, state: dict, stage: str, source: str) -> tuple[dict, list[dict]]:
        path = inside(self.root, source)
        report = read_json(path)
        require(report.get("schema_version") == REPORT_SCHEMA and report.get("stage") == stage,
                "Report schema_version or stage does not match")
        nonempty(report.get("summary"), "report.summary")
        require(report.get("status") == "pass", "Report must have status=pass before completion")
        artifacts = strings(report.get("artifacts"), "report.artifacts")
        details = report.get("details", {})
        require(isinstance(details, dict), "report.details must be an object")
        findings = report.get("findings", [])
        require(isinstance(findings, list), "report.findings must be an array")
        for finding in findings:
            require(isinstance(finding, dict) and finding.get("severity") in
                    {"blocker", "warning", "suggestion"}, "Invalid finding severity")
            nonempty(finding.get("message"), "finding.message")
            require(finding["severity"] != "blocker" or finding.get("resolved") is True,
                    "Unresolved blocker prevents stage completion")
        if stage in {"design_audit", "review"}:
            require("findings" in report, "An explicit findings array is required, including when empty")
        if stage == "intake":
            acceptance = strings(details.get("acceptance"), "intake.details.acceptance")
            module_waves(details.get("modules"))
            covered = set()
            for module in details["modules"]:
                claimed = strings(module.get("acceptance"), "module.acceptance")
                require(set(claimed) <= set(acceptance), "Module claims unknown acceptance criteria")
                covered.update(claimed)
            require(covered == set(acceptance), "Modules must cover every acceptance criterion")
            if not state["workflow"]["enabled"]["design"]:
                nonempty(details.get("approach"), "intake.details.approach (brief implementation approach)")
            if not state["workflow"]["enabled"]["test_design"]:
                nonempty(details.get("verification"), "intake.details.verification (how acceptance will be checked)")
            require(state["workflow"]["isolation"] != "checkout" or len(details["modules"]) == 1,
                    "Checkout isolation supports one module; use auto/worktree for multiple modules")
        elif stage == "design":
            modules = self.report_for(state, "intake")["details"]["modules"]
            designs = details.get("designs")
            require(isinstance(designs, dict) and set(designs) == {m["id"] for m in modules},
                    "design.details.designs must map every module ID to an artifact path")
            for name in designs.values():
                nonempty(name, "module design path")
            require(set(designs.values()) <= set(artifacts), "Every module design must be an artifact")
        elif stage == "test_design":
            acceptance = self.report_for(state, "intake")["details"]["acceptance"]
            scenarios = details.get("scenarios")
            require(isinstance(scenarios, list) and scenarios, "Test scenarios are required")
            covered, ids = set(), set()
            for scenario in scenarios:
                require(isinstance(scenario, dict), "Scenario must be an object")
                sid = nonempty(scenario.get("id"), "scenario.id")
                require(sid not in ids, "Duplicate scenario ID")
                ids.add(sid)
                claimed = strings(scenario.get("acceptance"), "scenario.acceptance")
                require(set(claimed) <= set(acceptance), "Scenario claims unknown acceptance criteria")
                covered.update(claimed)
            require(covered == set(acceptance), "Test scenarios must cover every acceptance criterion")
        elif stage == "plan":
            modules = self.report_for(state, "intake")["details"]["modules"]
            require(details.get("waves") == module_waves(modules), "Plan waves do not match module dependencies")
            tasks = details.get("tasks")
            require(isinstance(tasks, dict) and set(tasks) == {m["id"] for m in modules},
                    "Plan tasks must map every module ID to its implementation tasks")
            for module in modules:
                entries = tasks[module["id"]]
                require(isinstance(entries, list) and entries, "Each module needs implementation tasks")
                covered, ids = set(), set()
                for task in entries:
                    require(isinstance(task, dict), "Each task must be an object")
                    tid = identifier(task.get("id"))
                    require(tid not in ids, "Duplicate implementation task ID")
                    ids.add(tid)
                    nonempty(task.get("summary"), "task.summary")
                    nonempty(task.get("verification"), "task.verification")
                    claimed = strings(task.get("acceptance"), "task.acceptance")
                    require(set(claimed) <= set(module["acceptance"]), "Task claims unknown module acceptance")
                    covered.update(claimed)
                require(covered == set(module["acceptance"]), "Plan tasks must cover module acceptance criteria")
        elif stage == "implement":
            require(state["modules"] and all(m["status"] == "merged" for m in state["modules"].values()),
                    "All modules must be verified and merged through the wave executor")
            artifacts = list(artifacts)
            for module in state["modules"].values():
                verify_snapshots(self.root, module["evidence"])
                require(vcs.is_ancestor(self.root, module["head"]), "A merged module is missing from the owning branch")
                if state["execution_mode"] == "checkout":
                    require(vcs.fingerprint(self.root) == module["fingerprint"], "Module code changed after verification")
                artifacts.extend(e["path"] for e in module["evidence"])
        elif stage in {"review", "integration"}:
            self.check_receipts(state, report, stage)
            artifacts = [*artifacts, *(e["path"] for r in state["runs"] if r["id"] in report["checks"] for e in r["evidence"])]
        elif stage in ADAPTER_STAGES:
            receipt = self.adapter_receipt(state, report, stage)
            artifacts = [*artifacts, *(e["path"] for e in receipt["evidence"])]
        elif stage == "release":
            checks = details.get("checklist")
            require(isinstance(checks, dict), "release.details.checklist is required")
            for key in ("verification", "rollback", "observability", "risks"):
                item = checks.get(key)
                require(isinstance(item, dict) and item.get("status") in {"pass", "not_applicable"},
                        f"Release checklist {key} is not satisfied")
                nonempty(item.get("evidence"), f"release.checklist.{key}.evidence")
            if state["stages"]["pr"]["status"] == "done":
                require(state["stages"]["monitor"]["status"] == "done", "Release requires observed PR merge")
        elif stage == "knowledge":
            nonempty(details.get("outcome"), "knowledge.details.outcome")
            require(details["outcome"] in {"draft", "no_changes"}, "Knowledge outcome must be draft or no_changes")
        if stage in {"push", "pr", "monitor", "release", "deploy"}:
            require(vcs.clean(self.root), "Commit code changes before recording verification/delivery evidence")
        from .capabilities import stage_evidence
        evidence = snapshots(self.root, [str(path), *artifacts, *stage_evidence(self, state, stage, report)])
        return report, evidence

    def complete(self, stage: str, source: str, *, request_approval: bool = False) -> dict:
        with file_lock(self.lock_path):
            state = self.load()
            self.consistent(state)
            require(current(state) == stage and state["stages"][stage]["status"] == "running",
                    f"Enter the current stage ({current(state)}) before submitting its report")
            require(not any(r["status"] in {"running", "unresolved"} for r in state["runs"]),
                    "A command is still running; wait for its result before completing the stage")
            report, evidence = self.validate_report(state, stage, source)
            require(human_gate(state, stage, report) == request_approval,
                    "Approval intent does not match the selected stage policy")
            from .capabilities import finish_builtin
            finish_builtin(self, state, stage, source, report)
            item = state["stages"][stage]
            item.update(report=inside(self.root, source).relative_to(self.root).as_posix(),
                        evidence=evidence, fingerprint=vcs.fingerprint(self.root), head=vcs.head(self.root),
                        status="waiting_human" if request_approval else "done")
            if request_approval:
                item["approval_digest"] = digest({"config": state["config_hash"],
                                                  "evidence": evidence,
                                                  "upstream": [state["stages"][s].get("evidence")
                                                               for s in stage_order(state)[:stage_order(state).index(stage)]]})
            else:
                item["ended_at"] = now()
            if stage == "plan":
                state["waves"] = report["details"]["waves"]
                state["wave_index"] = 0
                state["modules"] = {m["id"]: {**m, "status": "pending"}
                                    for m in self.report_for(state, "intake")["details"]["modules"]}
                mode = state["workflow"]["isolation"]
                state["execution_mode"] = ("checkout" if len(state["modules"]) == 1 else "worktree") if mode == "auto" else mode
                state["plan_base"] = vcs.head(self.root)
            if stage == "knowledge" and not request_approval and report["details"]["outcome"] == "draft":
                from .knowledge import archive
                item["knowledge_archive"] = archive(self, item, report)
            self.save(state, "request_approval" if request_approval else "complete", stage=stage)
            return self.summary(state)

    def approve(self, stage: str, actor: str, note: str) -> dict:
        nonempty(actor, "actor")
        nonempty(note, "note (record the user's actual approval)")
        with file_lock(self.lock_path):
            state = self.load()
            self.consistent(state)
            require(stage in GATES and current(state) == stage, "No such current approval gate")
            item = state["stages"][stage]
            require(item["status"] == "waiting_human", "Submit concrete evidence before approval")
            verify_snapshots(self.root, item["evidence"])
            self.validate_report(state, stage, item["report"])
            if stage in CODE_BOUND:
                require(item["fingerprint"] == vcs.fingerprint(self.root), "Code changed while awaiting approval")
            item.update(status="done", ended_at=now(),
                        approval={"actor": actor, "note": note, "at": now(),
                                  "digest": item["approval_digest"]})
            if stage == "knowledge" and self.report_for(state, stage)["details"]["outcome"] == "draft":
                from .knowledge import archive
                item["knowledge_archive"] = archive(self, item, self.report_for(state, stage))
            self.save(state, "approve", stage=stage, actor=actor, note=note)
            return self.summary(state)

    def skip(self, stage: str, reason: str) -> dict:
        nonempty(reason, "reason")
        with file_lock(self.lock_path):
            state = self.load()
            self.consistent(state)
            require(stage in OPTIONAL and current(state) == stage, "This stage cannot be skipped")
            require(state["stages"][stage]["status"] != "waiting_human", "Resolve the pending approval first")
            require(not any(r["status"] in {"running", "unresolved"} for r in state["runs"]), "A command is still running")
            state["stages"][stage].update(status="skipped", reason=reason, ended_at=now())
            self.save(state, "skip", stage=stage, reason=reason)
            return self.summary(state)

    def fail(self, stage: str, reason: str) -> dict:
        nonempty(reason, "reason")
        with file_lock(self.lock_path):
            state = self.load()
            require(current(state) == stage and state["stages"][stage]["status"] == "running",
                    "Only the currently running stage can fail")
            state["stages"][stage].update(status="failed", reason=reason)
            self.save(state, "fail", stage=stage, reason=reason)
            return self.summary(state)

    def reset_from(self, state: dict, stage: str, reason: str) -> None:
        require(stage in STAGES, "Unknown stage")
        cur = current(state)
        order = stage_order(state)
        require(state["workflow"]["enabled"][stage], "Stage is excluded; use configure-flow to select it first")
        require(cur is None or order.index(stage) <= order.index(cur), "Cannot reopen a future stage")
        require(not any(r["status"] in {"running", "unresolved"} for r in state["runs"]),
                "A command is in flight; inspect it before reopening stages")
        affected = order[order.index(stage):]
        state["history"].append({"at": now(), "reason": reason,
                                 "stages": {s: copy.deepcopy(state["stages"][s]) for s in affected}})
        for name in affected:
            state["stages"][name] = policy_stage(state, name)
        if order.index(stage) <= order.index("plan"):
            state["history"][-1]["modules"] = state["modules"]
            state.update(modules={}, waves=[], wave_index=0)
            state.pop("wave_bases", None)
            state.pop("execution_mode", None)
        elif stage == "implement":
            # Worktrees remain on disk; a fresh epoch creates fresh branches when retrying.
            state["history"][-1]["modules"] = state["modules"]
            state["modules"] = {m["id"]: {**m, "status": "pending"} for m in
                                self.report_for(state, "intake")["details"]["modules"]}
            state["wave_index"] = 0
            state.pop("wave_bases", None)

    def reopen(self, stage: str, reason: str) -> dict:
        nonempty(reason, "reason")
        with file_lock(inside(self.root, ".harness/runs/start.lock")), file_lock(self.lock_path):
            state = self.load()
            self.reset_from(state, stage, reason)
            self.assert_sole_active(state)
            self.save(state, "reopen", stage=stage, reason=reason)
            return self.summary(state)

    def sync_config(self, reason: str) -> dict:
        nonempty(reason, "reason")
        with file_lock(inside(self.root, ".harness/runs/start.lock")), file_lock(self.lock_path):
            state = self.load(config_check=False)
            config = self.config
            if digest(config) == state["config_hash"]:
                return self.summary(state)
            previous = state["config"]
            affected = set()
            if config["host"] != previous["host"]:
                affected.add("plan" if state["modules"] else "review")
            if any(config[k] != previous[k] for k in ("checks", "stage_checks")):
                affected.add("implement" if any(m["status"] != "merged" for m in state["modules"].values()) else "review")
            for stage in ADAPTER_STAGES:
                if config["adapters"].get(stage) != previous["adapters"].get(stage):
                    affected.add(stage)
            # Committing changed project configuration changes HEAD and invalidates code evidence.
            affected.update(item["stage"] for item in self.stale(state) if item["stage"] in CODE_BOUND)
            workflow = resolve_workflow(config, state["workflow_overrides"])
            self.apply_policy(state, workflow, reason, affected)
            self.assert_sole_active(state)
            state.update(config=config, config_hash=digest(config), execution_hash=execution_hash(config))
            self.save(state, "sync_config", reason=reason)
            return self.summary(state)

    def apply_policy(self, state: dict, workflow: dict, reason: str, affected: set | None = None) -> None:
        require(not any(r["status"] in {"running", "unresolved"} for r in state["runs"]),
                "A command is in flight; inspect it before changing workflow configuration")
        old = state["workflow"]
        require(old.get("entry", "develop") == workflow["entry"],
                "Cannot change a task's entry; start a new task for a different scope")
        require(old["assistance"] == workflow["assistance"] or not state["modules"],
                "Choose assistance before implementation planning; an active task cannot weaken its checkpoints")
        changed = set(affected or ())
        changed.update(s for s in STAGES if old["enabled"][s] != workflow["enabled"][s])
        if old["order"] != workflow["order"] and workflow["enabled"]["integration"]:
            changed.update({"integration", "push"})
        if old["isolation"] != workflow["isolation"]:
            changed.add("plan")
        if old["knowledge_approval"] != workflow["knowledge_approval"]:
            changed.add("knowledge")
        for slot, stage in CAPABILITY_STAGES.items():
            if workflow["enabled"][stage] and (old["capabilities"][slot] != workflow["capabilities"][slot] or
                    (old["domain"] != workflow["domain"] and slot in {"design", "design_audit"})):
                changed.add(stage)
        if any(old["enabled"][s] and not workflow["enabled"][s] for s in ("design", "test_design")):
            changed.add("intake")  # Require the compact approach/verification now carried by intake.
        if workflow["isolation"] == "checkout" and state["stages"]["intake"]["status"] == "done":
            require(len(self.report_for(state, "intake")["details"]["modules"]) == 1,
                    "Checkout isolation supports one module; reopen intake to change module boundaries")
        # Reset an affected suffix, including excluded stages, without erasing earlier evidence.
        if changed:
            order = workflow["order"]
            first = min(order.index(s) for s in changed)
            suffix = order[first:]
            state["history"].append({"at": now(), "reason": reason, "workflow": copy.deepcopy(old),
                                     "stages": {s: copy.deepcopy(state["stages"][s]) for s in suffix}})
            state["workflow"] = workflow
            for stage in suffix:
                state["stages"][stage] = policy_stage(state, stage)
            if first <= order.index("implement"):
                state["history"][-1]["modules"] = state["modules"]
                state.pop("wave_bases", None)
                state["wave_index"] = 0
                if first <= order.index("plan"):
                    state.update(modules={}, waves=[])
                    state.pop("execution_mode", None)
                elif state["stages"]["plan"]["status"] == "done":
                    state["modules"] = {m["id"]: {**m, "status": "pending"} for m in
                                        self.report_for(state, "intake")["details"]["modules"]}
        state["workflow"] = workflow

    def configure_flow(self, options: dict, reason: str) -> dict:
        nonempty(reason, "reason")
        with file_lock(inside(self.root, ".harness/runs/start.lock")), file_lock(self.lock_path):
            state = self.load()
            old = state["workflow_overrides"]
            overrides = {**old, **options, "stages": {**old.get("stages", {}), **options.get("stages", {})},
                         "capabilities": {**old.get("capabilities", {}), **options.get("capabilities", {})}}
            workflow = resolve_workflow(state["config"], overrides)
            self.apply_policy(state, workflow, reason)
            self.assert_sole_active(state)
            state["workflow_overrides"] = overrides
            self.save(state, "configure_flow", reason=reason, workflow=workflow)
            return self.summary(state)

    def assert_sole_active(self, state: dict) -> None:
        if current(state) is None:
            return
        for path in inside(self.root, ".harness/runs").glob("*/state.json"):
            if path == self.path:
                continue
            other = read_json(inside(self.root, path))
            require(other.get("schema_version") == STATE_SCHEMA, "Unsupported task state in .harness/runs")
            require(other.get("branch") != state["branch"] or other.get("aborted") or current(other) is None,
                    f"Branch already has an active task: {other.get('task')}")

    def abort(self, reason: str) -> dict:
        nonempty(reason, "reason")
        with file_lock(self.lock_path):
            state = self.load(active=False, config_check=False)
            require(not any(r["status"] in {"running", "unresolved"} for r in state["runs"]),
                    "Wait for or inspect the running command before aborting")
            state["aborted"] = True
            self.save(state, "abort", reason=reason)
            return self.summary(state)

    def plan(self, tasks_source: str) -> dict:
        self.enter("plan")
        with file_lock(self.lock_path):
            state = self.load()
            modules = self.report_for(state, "intake")["details"]["modules"]
            tasks = read_json(inside(self.root, tasks_source))
            waves = module_waves(modules)
            path = inside(self.root, self.directory / "artifacts" / f"plan-{uuid.uuid4().hex[:8]}.json")
            atomic_json(path, {"modules": modules, "waves": waves, "tasks": tasks,
                               "parallel_max": state["config"]["parallel_max"]})
            report = path.with_name(path.stem + "-report.json")
            atomic_json(report, {"schema_version": REPORT_SCHEMA, "stage": "plan", "status": "pass",
                                 "summary": "Implementation tasks mapped to acceptance and dependency waves",
                                 "artifacts": [str(path)], "details": {"waves": waves, "tasks": tasks}})
        return self.complete("plan", str(report))
