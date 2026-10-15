"""Read-only coordination of independent repository workflows and shared check evidence."""
from __future__ import annotations

from pathlib import Path
import re

from . import git as vcs
from .engine import Workflow
from .model import HarnessError, identifier, module_waves, nonempty, now, require
from .storage import atomic_json, file_lock, inside, read_json, verify_snapshots


def path(root, group):
    return inside(root, f".harness/runs/groups/{identifier(group)}.json")


def link(root, source):
    manifest = read_json(inside(root, source))
    require(manifest.get("schema_version") == 1, "Expected group manifest schema_version=1")
    group = identifier(manifest.get("id"))
    nonempty(manifest.get("goal"), "group.goal")
    repositories = manifest.get("repositories")
    waves = module_waves(repositories)
    require(len(repositories) >= 2, "A repository group needs at least two repositories")
    known, git_roots, entries = set(), set(), []
    for repo in repositories:
        require(Path(repo.get("path", "")).is_absolute(), "Repository paths must be explicit absolute paths")
        checkout = vcs.repo_root(Path(repo["path"]))
        common = vcs.common_dir(checkout)
        require(common not in git_roots, "Use modules for worktrees of the same Git repository")
        git_roots.add(common)
        flow = Workflow(checkout, repo.get("task"))
        state = flow.load()
        flow.consistent(state)
        revision = repo.get("revision", "")
        require(isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision) and revision == vcs.head(checkout),
                "Pin each repository to its current full commit SHA")
        require(vcs.clean(checkout), "Commit each repository before pinning the shared integration baseline")
        entries.append({"id": repo["id"], "path": str(checkout), "task": flow.task,
                        "revision": revision, "depends_on": repo.get("depends_on", []),
                        "git_common_dir": common, "prior_runs": [r["id"] for r in state["runs"]]})
        known.add(repo["id"])
    contracts = manifest.get("contracts", [])
    require(isinstance(contracts, list), "group.contracts must be an array")
    for contract in contracts:
        require(isinstance(contract, dict) and contract.get("producer") in known and contract.get("consumer") in known,
                "Contracts must name known producer/consumer repositories")
        consumer = next(r for r in entries if r["id"] == contract["consumer"])
        require(contract["producer"] in consumer["depends_on"], "Contract producer must be a consumer dependency")
        nonempty(contract.get("path"), "contract.path")
        nonempty(contract.get("expected"), "contract.expected (explicit version or revision in the dependency declaration)")
        inside(Path(consumer["path"]), contract["path"])
    check = manifest.get("integration")
    require(isinstance(check, dict) and check.get("repository") in known, "Select a shared integration repository")
    nonempty(check.get("check"), "integration.check")
    selected = next(r for r in entries if r["id"] == check["repository"])
    selected_state = Workflow(Path(selected["path"]), selected["task"]).load()
    require(check["check"] in selected_state["config"]["stage_checks"].get("integration", []) and
            selected_state["workflow"]["enabled"]["integration"],
            "Shared integration must be a configured, selected integration check")
    destination = path(root, group)
    with file_lock(destination.with_suffix(".lock")):
        require(not destination.exists(), "Group already exists; use a new group ID when pins change")
        atomic_json(destination, {"schema_version": 1, "id": group, "goal": manifest["goal"],
                                  "repositories": entries, "waves": waves, "contracts": contracts,
                                  "integration": check, "created_at": now(), "checks": []})
    return status(root, group)


def inspect(group):
    observations, problems, states = [], [], {}
    for repo in group["repositories"]:
        try:
            flow = Workflow(Path(repo["path"]), repo["task"])
            state = flow.load()
            require(vcs.common_dir(flow.root) == repo["git_common_dir"], "Repository identity changed")
            require(vcs.head(flow.root) == repo["revision"], "Pinned revision changed; create a new group")
            require(vcs.clean(flow.root), "Repository has uncommitted changes")
            flow.consistent(state)
            summary = flow.summary(state)
            observations.append({"id": repo["id"], "revision": repo["revision"], "task": flow.task,
                                 "status": summary["status"], "stage": summary["current_stage"]})
            states[repo["id"]] = (flow, state)
        except (HarnessError, OSError, ValueError) as error:
            problems.append({"repository": repo["id"], "reason": str(error)})
    for contract in group["contracts"]:
        try:
            repo = next(r for r in group["repositories"] if r["id"] == contract["consumer"])
            file = inside(Path(repo["path"]), contract["path"])
            require(file.is_file() and file.stat().st_size <= 2 * 1024 * 1024,
                    "Dependency declaration is missing or too large")
            require(contract["expected"] in file.read_text(), "Expected dependency version/revision is absent")
        except (HarnessError, OSError, ValueError) as error:
            problems.append({"contract": contract, "reason": str(error)})
    return observations, problems, states


def check_receipt(group, states, repository, run_id):
    require(repository == group["integration"]["repository"] and repository in states,
            "Shared check must run in the selected integration repository")
    flow, state = states[repository]
    receipt = next((r for r in state["runs"] if r["id"] == run_id), None)
    repo = next(r for r in group["repositories"] if r["id"] == repository)
    require(receipt and receipt["id"] not in repo["prior_runs"] and not receipt.get("reused_from"),
            "Execute a new shared integration check after linking these repository pins")
    require(receipt["kind"] == "check" and receipt["stage"] == "integration" and
            receipt["name"] == group["integration"]["check"] and receipt["status"] == "passed" and
            receipt.get("module") is None, "Shared integration check did not pass")
    require(receipt["fingerprint"] == vcs.fingerprint(flow.root) and
            receipt["config_hash"] == state["execution_hash"] and
            receipt["epoch"] == state["stages"]["integration"]["epoch"], "Shared integration evidence is stale")
    verify_snapshots(flow.root, receipt["evidence"])
    return receipt


def record(root, group_id, repository, run_id):
    destination = path(root, group_id)
    with file_lock(destination.with_suffix(".lock")):
        group = read_json(destination)
        _, problems, states = inspect(group)
        require(not problems, f"Repository group is not current: {problems}")
        receipt = check_receipt(group, states, repository, run_id)
        item = {"repository": repository, "run_id": run_id, "recorded_at": now(),
                "pins": {r["id"]: r["revision"] for r in group["repositories"]},
                "evidence": receipt["evidence"]}
        if not any(c["run_id"] == run_id for c in group["checks"]):
            group["checks"].append(item)
            atomic_json(destination, group)
    return status(root, group_id)


def status(root, group_id):
    group = read_json(path(root, group_id))
    observations, problems, states = inspect(group)
    passed = []
    for check in group["checks"]:
        try:
            check_receipt(group, states, check["repository"], check["run_id"])
            passed.append({"repository": check["repository"], "run_id": check["run_id"]})
        except (HarnessError, OSError, ValueError) as error:
            problems.append({"run_id": check["run_id"], "reason": str(error)})
    complete = all(r["status"] == "complete" for r in observations) and len(observations) == len(group["repositories"])
    return {"group": group_id, "goal": group["goal"], "waves": group["waves"],
            "repositories": observations, "contracts": group["contracts"], "shared_checks": passed,
            "problems": problems, "status": "stale" if problems else
            ("verified" if complete and passed else "awaiting_integration" if not passed else "in_progress"),
            "evidence_boundary": "Dependency declarations and the configured check are verified; inspect its assertions for behavioral coverage"}
