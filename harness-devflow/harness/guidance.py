"""Small, deterministic work packets for guided and autonomous agents."""
from __future__ import annotations

from pathlib import Path
import sys
import uuid

from . import git as vcs
from .engine import current, human_gate, stage_order
from .hosts import resolve
from .model import CAPABILITY_STAGES, REPORT_SCHEMA, require
from .storage import atomic_json, file_lock, inside, read_json


def command(workflow, *args) -> list[str]:
    return [sys.executable, str(Path(__file__).resolve().parent.parent / "scripts/harness.py"),
            "--repo", str(workflow.root), "--task", workflow.task, *args]


def packet(workflow, state: dict) -> dict:
    from .cli import skill_for
    from .context import references
    stage = current(state)
    summary = workflow.summary(state)
    inputs = references(workflow, state)
    result = {"task": workflow.task, "goal": state["goal"], "repository": str(workflow.root),
              "head": vcs.head(workflow.root), "fingerprint": vcs.fingerprint(workflow.root),
              "initial_dirty": state["initial_dirty"], "assistance": state["workflow"]["assistance"],
              "execution": resolve(state["config"]["host"], state["workflow"]["assistance"]),
              "status": summary["status"], "stage": stage, "inputs": inputs,
              "quality": "Only current code-bound check receipts and accepted artifacts satisfy completion"}
    result["history_command"] = command(workflow, "context", "--all")
    if state.get("review_context"):
        result["review_context"] = state["review_context"]
    if not stage or state["aborted"]:
        result["action"] = {"kind": "finished"}
        return result
    if summary["stale"]:
        result["action"] = {"kind": "repair_evidence", "problems": summary["stale"]}
        return result
    unresolved = [r for r in state["runs"] if r["status"] in {"running", "unresolved"}]
    if unresolved:
        result["action"] = {"kind": "inspect_execution", "runs": unresolved}
        return result
    if state["stages"][stage]["status"] in {"waiting_human", "failed"}:
        result["action"] = {"kind": "approval" if state["stages"][stage]["status"] == "waiting_human" else "diagnose",
                            "stage": stage, "details": state["stages"][stage]}
        return result
    base = Path(__file__).resolve().parent.parent
    result["skill"] = str(base / "skills" / skill_for(stage) / "SKILL.md")
    result["checks"] = state["config"]["stage_checks"].get(stage, [])
    for slot, mapped in CAPABILITY_STAGES.items():
        if mapped == stage:
            from .capabilities import selection
            result["professional_method"] = {"slot": slot, **selection(workflow, state, slot)}
    if stage == "implement":
        wave = state["waves"][state["wave_index"]] if state["wave_index"] < len(state["waves"]) else []
        active = [mid for mid in wave if state["modules"][mid]["status"] in {"running", "awaiting_host"}]
        pending = [mid for mid in wave if state["modules"][mid]["status"] == "pending"]
        candidates = active + pending
        result["ready_modules"] = candidates if result["execution"]["delegation"] == "native" else candidates[:1]
        if not candidates:
            result["action"] = {"kind": "merge_wave" if wave else "submit_stage",
                                "command": command(workflow, "merge-wave") if wave else None}
            return result
        mid = candidates[0]
        module = state["modules"][mid]
        tasks = workflow.report_for(state, "plan")["details"]["tasks"][mid]
        done = {c["task"] for c in module.get("checkpoints", [])}
        remaining = [t for t in tasks if t["id"] not in done]
        result["module"] = mid
        result["inputs"] = references(workflow, state, module=mid)
        result["worktree"] = module.get("worktree")
        result["acceptance"] = module["acceptance"]
        result["tasks"] = remaining[:1] if result["assistance"] == "guided" else remaining
        result["check_commands"] = [command(workflow, "run-check", name, "--module", mid)
                                    for name in state["config"]["stage_checks"].get("review", [])]
        if module["status"] == "pending":
            action = {"kind": "prepare_module", "command": command(workflow, "prepare-module", mid)}
        elif module["status"] == "awaiting_host":
            action = {"kind": "host_worktree", "request": module["request"]}
        else:
            action = {"kind": "implement_task" if remaining else "submit_module",
                      "instruction": "Implement the listed behavior, run checks, and record a checkpoint with actual artifacts"}
        result["action"] = action
    else:
        result["action"] = {"kind": "execute_skill", "completion": command(workflow, "submit", "--result", "<result.json>")}
    return result


def advance(workflow) -> dict:
    with file_lock(workflow.lock_path):
        state = workflow.load(active=False, config_check=False)
        result = packet(workflow, state)
    if result["stage"] and result["status"] == "pending" and result["action"]["kind"] not in {"inspect_execution", "repair_evidence"}:
        workflow.enter(result["stage"])
        with file_lock(workflow.lock_path):
            result = packet(workflow, workflow.load())
    return result


def submit(workflow, source: str) -> dict:
    """Build the machine envelope and select real receipts; semantic findings remain explicit."""
    raw = read_json(inside(workflow.root, source))
    require("schema_version" not in raw and "stage" not in raw,
            "Submit a result body, without a schema_version or stage envelope")
    with file_lock(workflow.lock_path):
        state = workflow.load()
        stage = current(state)
        require(stage is not None, "Task is already complete")
    workflow.enter(stage)
    with file_lock(workflow.lock_path):
        state = workflow.load()
        require(current(state) == stage, "Task advanced during submission")
        report = {"schema_version": REPORT_SCHEMA, "stage": stage, **raw}
        code = vcs.fingerprint(workflow.root)
        eligible = [r for r in state["runs"] if r["stage"] == stage and
                    r["epoch"] == state["stages"][stage]["epoch"] and r["status"] == "passed" and
                    r["fingerprint"] == code and r["config_hash"] == state["execution_hash"] and r.get("module") is None]
        if stage in {"review", "integration"} and "checks" not in report:
            # Older passing receipts can have expired reuse inputs. Keep only the
            # newest candidate for each command; core validation still rejects failures.
            latest_checks = {r["name"]: r["id"] for r in eligible if r["kind"] == "check"}
            report["checks"] = list(latest_checks.values())
        adapters = [r for r in eligible if r["kind"] == "adapter"]
        if adapters and "adapter_run" not in report:
            report["adapter_run"] = adapters[-1]["id"]
        target = workflow.directory / "artifacts" / f"{stage}-{state['stages'][stage]['epoch']}-{uuid.uuid4().hex[:12]}-report.json"
        atomic_json(target, report)
        approval = human_gate(state, stage, report)
    return workflow.complete(stage, str(target), request_approval=approval)


def submit_batch(workflow, source: str) -> dict:
    require(workflow.load()["workflow"]["assistance"] == "autonomous", "Batch submission requires autonomous assistance")
    from .model import strings
    sources = strings(read_json(inside(workflow.root, source)).get("results"), "batch.results")
    require(len(sources) <= 16, "Batch is bounded to 16 results")
    results = []
    for source in sources:
        results.append(submit(workflow, source))
        if results[-1]["status"] == "waiting_human":
            break
    return {"status": results[-1]["status"], "submitted": len(results), "remaining": sources[len(results):], "results": results}


def handoff(workflow, output: str) -> dict:
    with file_lock(workflow.lock_path):
        data = packet(workflow, workflow.load(active=False, config_check=False))
        target = inside(workflow.root, output)
        require(not target.exists(), "Choose a new handoff output path")
        atomic_json(target, data)
    return {"output": str(target), "instruction": "Read this packet in the same checkout with any supported host; run next to revalidate"}
