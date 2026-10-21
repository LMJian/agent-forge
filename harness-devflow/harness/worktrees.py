"""Dependency-wave worktree execution, completion and resumable merging."""
from __future__ import annotations

from . import git as vcs
from .hosts import module_path, resolve
from .engine import Workflow, current
from .model import nonempty, now, require, strings, REPORT_SCHEMA
from .storage import file_lock, inside, read_json, snapshots, verify_snapshots


def executing(workflow: Workflow, state: dict) -> list[str]:
    workflow.consistent(state)
    require(not any(r["status"] == "unresolved" for r in state["runs"]),
            "An execution outcome is unresolved; reconcile it before module operations")
    require(current(state) == "implement" and state["stages"]["implement"]["status"] == "running",
            "Module execution is available only during implement, after the selected planning stages")
    require(state["wave_index"] < len(state["waves"]), "All waves are already merged")
    return state["waves"][state["wave_index"]]


def prepare(workflow: Workflow, module: str) -> dict:
    with file_lock(workflow.lock_path):
        state = workflow.load()
        wave = executing(workflow, state)
        require(module in wave, f"Module is not in the current wave: {wave}")
        item = state["modules"][module]
        require(item["status"] in {"pending", "awaiting_host", "running"}, "Module is already verified")
        execution = resolve(state["config"]["host"], state["workflow"]["assistance"])
        if execution["delegation"] == "serial":
            require(not any(mid != module and m["status"] in {"running", "awaiting_host"}
                            for mid, m in state["modules"].items()), "Serial execution: finish the active module first")
        if state["execution_mode"] == "checkout":
            if item.get("worktree"):
                require(vcs.branch(workflow.root) == item["branch"], "Owning checkout branch changed")
                return item
            item.update(status="running", branch=state["branch"], worktree=str(workflow.root),
                        provider="builtin", execution_mode="checkout", base=vcs.head(workflow.root),
                        initial_fingerprint=vcs.fingerprint(workflow.root), checkpoints=[], started_at=now())
            workflow.save(state, "module_prepared", module=module, execution_mode="checkout")
            return item
        epoch = state["stages"]["implement"]["epoch"]
        path = inside(workflow.root, f".harness/worktrees/{workflow.task}/{epoch}/{module}")
        branch = f"harness/{workflow.task}/{epoch}/{module}"
        if item.get("worktree"):
            require(module_path(workflow, item).is_dir(), "Worktree missing")
            return item
        from .branches import require_approval
        require_approval(state, module=module)
        require(vcs.clean(workflow.root), "The owning branch must be clean before preparing a wave")
        base = state.setdefault("wave_bases", {}).setdefault(str(state["wave_index"]), vcs.head(workflow.root))
        require(vcs.head(workflow.root) == base, "Owning branch moved while preparing this wave")
        if execution["worktree"] == "native":
            item.update(status="awaiting_host", provider="native", base=base, checkpoints=[],
                        request={"operation": "create_worktree", "repository": str(workflow.root),
                                 "task": workflow.task, "module": module, "base_sha": base,
                                 "instruction": "Use the available host worktree tool at this exact base; attach the resulting path"})
            workflow.save(state, "native_worktree_requested", module=module)
            return item
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            # Recover a process death after git worktree add but before the state transaction.
            require(vcs.repo_root(path) == path and vcs.branch(path) == branch and
                    vcs.is_ancestor(path, base), "Existing path is not this module's worktree")
        else:
            vcs.git(workflow.root, "worktree", "add", "-b", branch, str(path), base)
        item.update(status="running", provider="builtin", branch=branch, worktree=str(path), base=base,
                    initial_fingerprint=vcs.fingerprint(path), checkpoints=[], started_at=now())
        workflow.save(state, "module_prepared", module=module)
        return item


def attach(workflow: Workflow, module: str, path: str) -> dict:
    """Adopt only an explicitly requested, clean host worktree at the required wave base."""
    from pathlib import Path
    with file_lock(workflow.lock_path):
        state = workflow.load()
        require(module in executing(workflow, state), "Module is not in the current wave")
        item = state["modules"][module]
        require(item["status"] == "awaiting_host" and item["provider"] == "native", "No native worktree request")
        from .branches import require_approval
        require_approval(state, module=module)
        proposed = {**item, "worktree": str(Path(path).resolve()), "branch": vcs.branch(Path(path))}
        location = module_path(workflow, proposed)
        require(vcs.head(location) == item["base"] and vcs.clean(location),
                "Native worktree must be clean at the requested base SHA")
        require(vcs.head(workflow.root) == item["base"] and vcs.clean(workflow.root), "Owning wave base changed")
        require(not any(m.get("worktree") == str(location) for m in state["modules"].values()),
                "A worktree can belong to only one module")
        item.update(proposed, status="running", initial_fingerprint=vcs.fingerprint(location), started_at=now())
        workflow.save(state, "native_worktree_attached", module=module, worktree=str(location))
        return item


def checkpoint(workflow: Workflow, module: str, step: str, summary: str, checks: list[str], artifacts: list[str]) -> dict:
    nonempty(summary, "checkpoint.summary")
    with file_lock(workflow.lock_path):
        state = workflow.load()
        require(module in executing(workflow, state), "Module is not in the current wave")
        item = state["modules"][module]
        require(item["status"] == "running", "Prepare the module first")
        path = module_path(workflow, item)
        tasks = workflow.report_for(state, "plan")["details"]["tasks"][module]
        recorded = item["checkpoints"]
        require(len(recorded) < len(tasks) and tasks[len(recorded)]["id"] == step,
                "Checkpoint must match the next planned task ID")
        for entry in recorded:
            verify_snapshots(workflow.root, entry["evidence"])
        require(not any(r["status"] in {"running", "unresolved"} and r.get("module") == module for r in state["runs"]),
                "A module check is still running")
        code = vcs.fingerprint(path)
        logs = []
        for run_id in strings(checks, "checkpoint.checks"):
            receipt = next((r for r in state["runs"] if r["id"] == run_id), None)
            require(receipt and receipt["kind"] == "check" and receipt.get("module") == module and
                    receipt["stage"] == "implement" and receipt["epoch"] == state["stages"]["implement"]["epoch"] and
                    receipt["status"] == "passed" and receipt["fingerprint"] == code and
                    receipt["config_hash"] == state["execution_hash"], "Checkpoint requires a current passed module check")
            verify_snapshots(workflow.root, receipt["evidence"])
            logs.extend(e["path"] for e in receipt["evidence"])
        recorded.append({"task": step, "summary": summary, "checks": checks, "fingerprint": code, "at": now(),
                         "evidence": snapshots(workflow.root, [*strings(artifacts, "checkpoint.artifacts"), *logs])})
        workflow.save(state, "task_checkpoint", module=module, step=step)
        return recorded[-1]


def complete(workflow: Workflow, module: str, source: str) -> dict:
    with file_lock(workflow.lock_path):
        state = workflow.load()
        wave = executing(workflow, state)
        require(module in wave, "Module is not in the current wave")
        item = state["modules"][module]
        require(item["status"] == "running", "Prepare the module before completing it")
        path = module_path(workflow, item)
        sha = vcs.head(path)
        if state["execution_mode"] == "worktree":
            require(vcs.clean(path), "Commit module changes before merging a worktree")
            require(sha != item["base"] and vcs.is_ancestor(path, item["base"]), "Module needs its own implementation commit")
        else:
            require(vcs.is_ancestor(path, item["base"]) and vcs.fingerprint(path) != item["initial_fingerprint"],
                    "Module needs an implementation change")
        report = read_json(inside(workflow.root, source))
        require(report.get("schema_version") == REPORT_SCHEMA and report.get("module") == module and
                report.get("status") == "pass", "Invalid module completion report")
        nonempty(report.get("summary"), "module.summary")
        tasks = strings(report.get("completed_tasks"), "module.completed_tasks")
        planned = workflow.report_for(state, "plan")["details"]["tasks"][module]
        require(set(tasks) == {t["id"] for t in planned}, "Completion must cover the planned task IDs")
        if state["workflow"]["assistance"] == "guided":
            require([c["task"] for c in item["checkpoints"]] == [t["id"] for t in planned],
                    "Guided execution requires verified checkpoints for every planned task")
        for entry in item["checkpoints"]:
            verify_snapshots(workflow.root, entry["evidence"])
        coverage = strings(report.get("acceptance"), "module.acceptance")
        require(set(coverage) == set(item["acceptance"]), "Module completion must cover its assigned acceptance criteria")
        artifact_names = strings(report.get("artifacts"), "module.artifacts")
        artifact_names = [*artifact_names, *(e["path"] for entry in item["checkpoints"] for e in entry["evidence"])]
        check_ids = strings(report.get("checks"), "module.checks")
        required = state["config"]["stage_checks"].get("review", [])
        require(required, "Configure review checks before implementing modules")
        found = set()
        code = vcs.fingerprint(path)
        for run_id in check_ids:
            receipt = next((r for r in state["runs"] if r["id"] == run_id), None)
            require(receipt and receipt["kind"] == "check" and receipt["module"] == module and
                    receipt["stage"] == "implement" and receipt["status"] == "passed" and
                    receipt["epoch"] == state["stages"]["implement"]["epoch"] and
                    receipt["config_hash"] == state["execution_hash"] and receipt["fingerprint"] == code,
                    f"Missing, failed or stale module check: {run_id}")
            found.add(receipt["name"])
            verify_snapshots(workflow.root, receipt["evidence"])
            artifact_names.extend(e["path"] for e in receipt["evidence"])
        require(set(required) <= found, f"Missing module checks: {sorted(set(required) - found)}")
        item.update(status="verified", head=sha, fingerprint=code, completed_tasks=tasks,
                    evidence=snapshots(workflow.root, [source, *artifact_names]))
        if state["execution_mode"] == "checkout":
            item.update(status="merged", merged_at=now())
            state["wave_index"] += 1
        workflow.save(state, "module_verified", module=module)
        return item


def merge_wave(workflow: Workflow) -> dict:
    with file_lock(workflow.lock_path):
        state = workflow.load()
        wave = executing(workflow, state)
        require(all(state["modules"][mid]["status"] in {"verified", "merged"} for mid in wave),
                "Every module in the wave must be verified before merging")
        require(not any(r["status"] in {"running", "unresolved"} for r in state["runs"]), "Checks are still running")
        require(vcs.clean(workflow.root), "Resolve any merge conflicts and commit before resuming wave merge")
        for mid in wave:
            item = state["modules"][mid]
            path = module_path(workflow, item)
            verify_snapshots(workflow.root, item["evidence"])
            require(vcs.fingerprint(path) == item["fingerprint"], f"Module {mid} changed after verification")
            if not vcs.is_ancestor(workflow.root, item["head"]):
                try:
                    vcs.git(workflow.root, "merge", "--no-ff", "--no-edit", item["head"])
                except Exception:
                    workflow.save(state, "merge_interrupted", module=mid)
                    raise
            item.update(status="merged", merged_at=now())
            workflow.save(state, "module_merged", module=mid)
        state["wave_index"] += 1
        workflow.save(state, "wave_merged", wave_index=state["wave_index"] - 1)
        return workflow.summary(state)
