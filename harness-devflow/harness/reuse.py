"""Opt-in reuse of deterministic local checks; never reuse external actions or reviews."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import platform
import shutil
import uuid

from . import git as vcs
from .engine import current
from .hosts import resolve
from .model import digest, require, now
from .storage import file_lock, inside, verify_snapshots


def inputs(workflow, state: dict, spec: dict, cwd: Path) -> dict | None:
    policy = spec.get("reuse")
    if policy is None:
        return None
    require(resolve(state["config"]["host"], state["workflow"]["assistance"])["command"] == "builtin",
            "Reusable checks require builtin local execution; native environments need fresh checks")
    executable = spec["argv"][0].replace("{repo}", str(workflow.root)).replace(
        "{plugin_root}", str(Path(__file__).resolve().parent.parent))
    resolved = (cwd / executable).resolve() if "/" in executable else shutil.which(executable)
    require(resolved and Path(resolved).is_file(), "Cannot fingerprint check executable")
    files = []
    for name in policy["context_files"]:
        path = inside(cwd, name)
        require(path.is_file(), f"Declared reusable check input is missing: {name}")
        files.append({"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    # Hash environment values; never persist secrets themselves. Harness-generated
    # variables are excluded only under the explicitly declared deterministic policy.
    environment = {k: v for k, v in os.environ.items() if not k.startswith("HARNESS_")}
    return {"version": 1, "content": vcs.content_fingerprint(cwd), "cwd": str(cwd),
            "executable": str(Path(resolved).resolve()),
            "executable_sha256": hashlib.sha256(Path(resolved).read_bytes()).hexdigest(),
            "platform": platform.platform(), "environment": digest(environment),
            "context_files": files, "command": digest(spec), "config": state["execution_hash"]}


def reuse(workflow, name: str, source_id: str) -> dict:
    with file_lock(workflow.lock_path):
        state = workflow.load()
        workflow.consistent(state)
        stage = current(state)
        require(stage in {"review", "integration"} and state["stages"][stage]["status"] == "running",
                "Reuse requires a running local review or integration stage")
        require(not any(r["status"] in {"running", "unresolved"} for r in state["runs"]),
                "Resolve in-flight commands before reusing checks")
        require(name in state["config"]["stage_checks"].get(stage, []), "Check is not assigned to this stage")
        spec = state["config"]["checks"][name]
        cross_stage = spec.get("reuse", {}).get("across_stages", False)
        require(stage == "review" or cross_stage, "Integration reuse requires explicit across_stages policy")
        source = next((r for r in state["runs"] if r["id"] == source_id), None)
        require(source and source["kind"] == "check" and source["name"] == name and
                source["status"] == "passed" and source["cwd"] == str(workflow.root) and
                ((source["stage"] == "review" and source.get("module") is None) or
                 (cross_stage and source["stage"] in {"implement", "review", "integration"})),
                "Reuse requires a successful review check from this task and checkout")
        require(not source.get("reused_from"), "Select the original executed check, not a reused receipt")
        require(source.get("reuse_inputs"), "This check was not executed with an explicit reuse policy")
        require(not any(r["kind"] == "check" and r["name"] == name and r["status"] == "failed"
                        for r in state["runs"][state["runs"].index(source) + 1:]),
                "A newer failed check supersedes this result; execute a fresh check")
        current_inputs = inputs(workflow, state, spec, workflow.root)
        require(current_inputs == source["reuse_inputs"], "Check inputs, configuration or environment changed; execute a fresh check")
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(source["finished_at"])).total_seconds()
        require(0 <= age <= min(spec["reuse"]["max_age_seconds"], state["config"]["review_max_age_seconds"]),
                "Original check expired; execute a fresh check")
        verify_snapshots(workflow.root, source["evidence"])
        receipt = {**source, "id": uuid.uuid4().hex, "stage": stage, "module": None,
                   "epoch": state["stages"][stage]["epoch"],
                   "fingerprint": vcs.fingerprint(workflow.root), "head": vcs.head(workflow.root),
                   "reused_from": source_id, "reused_at": now()}
        # Keep original started_at, finished_at, logs and duration: reuse is not execution.
        state["runs"].append(receipt)
        workflow.save(state, "check_reused", run_id=receipt["id"], source_id=source_id)
        return receipt


def validate_receipt(workflow, state, receipt):
    """Recheck inputs/age at submission and delivery, not only when requesting reuse."""
    if not receipt.get("reuse_inputs"):
        return
    spec = state["config"]["checks"][receipt["name"]]
    require(inputs(workflow, state, spec, workflow.root) == receipt["reuse_inputs"],
            "Check inputs or environment changed after execution")
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(receipt["finished_at"])).total_seconds()
    require(0 <= age <= min(spec["reuse"]["max_age_seconds"], state["config"]["review_max_age_seconds"]),
            "Reusable check evidence expired")
