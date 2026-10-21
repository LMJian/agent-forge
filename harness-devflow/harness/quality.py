"""Codex feasibility contract and a code-bound acceptance ledger, not a test-count gate."""
from collections import Counter
import uuid

from . import git as vcs
from .model import HarnessError, identifier, nonempty, now, require, strings
from .storage import file_lock, inside, read_json, snapshots, verify_snapshots


def enabled(state):
    return state["workflow"]["profile"] == "codex" and state["workflow"]["entry"] == "develop"


def validate_tasks(modules, tasks):
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


def validate_intake(workflow, state, details, artifacts):
    """Require observed critical-risk probes and product outcomes before planning."""
    validate_tasks(details["modules"], details.get("tasks"))
    feasibility = details.get("feasibility")
    require(isinstance(feasibility, dict), "Codex intake requires feasibility")
    nonempty(feasibility.get("assessment"), "feasibility.assessment")
    risks = feasibility.get("risks")
    require(isinstance(risks, list), "feasibility.risks must be an array (empty only with a low-risk assessment)")
    ids = set()
    for risk in risks:
        require(isinstance(risk, dict), "Risk must be an object")
        rid = identifier(risk.get("id"))
        require(rid not in ids, "Duplicate risk ID")
        ids.add(rid)
        nonempty(risk.get("assumption"), "risk.assumption")
        require(type(risk.get("critical")) is bool, "risk.critical must be boolean")
        require(risk.get("status") in {"proven", "unproven", "excluded"}, "Invalid risk status")
        if risk["status"] == "excluded":
            nonempty(risk.get("authorization"), "risk.authorization (actual user scope decision)")
        elif risk["critical"]:
            require(risk["status"] == "proven", f"Critical feasibility risk {rid} is unproven; run a spike or change scope")
        if risk["status"] == "proven":
            for key in ("experiment", "expected", "observed"):
                nonempty(risk.get(key), f"risk.{key}")
            paths = strings(risk.get("evidence"), "risk.evidence")
            require(set(paths) <= set(artifacts), "Risk evidence must be included in intake artifacts")
            # A prose claim alone is insufficient for a critical technical assumption.
            if risk["critical"]:
                for run_id in strings(risk.get("checks"), "risk.checks"):
                    receipt = valid_check(workflow, state, run_id)
                    require(receipt["stage"] == "intake" and
                            receipt["epoch"] == state["stages"]["intake"]["epoch"],
                            "Critical risk needs a current intake probe, not an old unit-test receipt")
    scenarios = details.get("scenarios")
    require(isinstance(scenarios, list) and scenarios, "Codex intake requires scenarios")
    covered, product, ids = set(), set(), set()
    for case in scenarios:
        require(isinstance(case, dict), "Scenario must be an object")
        sid = identifier(case.get("id"))
        require(sid not in ids, "Duplicate scenario ID")
        ids.add(sid)
        claims = strings(case.get("acceptance"), "scenario.acceptance")
        require(set(claims) <= set(details["acceptance"]), "Scenario claims unknown acceptance")
        covered.update(claims)
        require(case.get("level") in {"component", "product"}, "Scenario needs component or product level")
        if case["level"] == "product":
            product.update(claims)
        for field in ("procedure", "expected", "environment"):
            nonempty(case.get(field), f"scenario.{field}")
        require(case.get("executor") in {"command", "agent", "human"}, "Unknown scenario executor")
        if case["executor"] == "command":
            require(case.get("check") in state["config"]["stage_checks"].get("review", []),
                    "Scenario command must be a configured final review check")
        elif case["executor"] == "human":
            nonempty(case.get("reason"), "human scenario.reason (why CLI/API/authorized automation cannot do it)")
            identifier(case.get("batch"))
    require(covered == set(details["acceptance"]), "Scenarios must cover every acceptance criterion")
    require(product == covered, "Every acceptance criterion needs product-level evidence; unit/build checks alone are insufficient")
    validate_journey(state, details, scenarios)


def validate_journey(state, details, scenarios):
    """Pin the actual user entry and final side effect, not just a 'product' label."""
    journey = details.get("journey")
    require(isinstance(journey, dict), "Codex intake requires a journey from user entry to terminal outcome")
    for key in ("entry", "terminal_outcome"):
        nonempty(journey.get(key), f"journey.{key}")
    steps = journey.get("steps")
    require(isinstance(steps, list) and steps, "journey.steps must describe observable outcomes")
    by_id, covered = {}, set()
    for step in steps:
        require(isinstance(step, dict), "Journey step must be an object")
        sid = identifier(step.get("id"))
        require(sid not in by_id, "Duplicate journey step")
        nonempty(step.get("outcome"), "journey step.outcome")
        require(step.get("proof") in {"artifact", "runtime"}, "Journey steps need artifact or runtime evidence")
        claims = strings(step.get("acceptance"), "journey step.acceptance")
        require(set(claims) <= set(details["acceptance"]), "Journey step claims unknown acceptance")
        covered.update(claims)
        by_id[sid] = step
    require(covered == set(details["acceptance"]), "Journey must include every accepted outcome")
    witnessed = set()
    for case in scenarios:
        if case["level"] != "product":
            continue
        proof = case.get("proof")
        require(proof in {"artifact", "runtime"}, "Product scenarios need artifact or runtime proof, not unit/build labels")
        nonempty(case.get("oracle"), "scenario.oracle (independent expected result and its source)")
        ids = strings(case.get("steps"), "scenario.steps")
        require(set(ids) <= set(by_id), "Scenario covers an unknown journey step")
        if case["executor"] == "command":
            require(state["config"]["checks"][case["check"]].get("proof") == proof,
                    "Scenario proof must match its configured check boundary; compilation/replay cannot stand in for runtime")
        claims = set()
        for sid in ids:
            step = by_id[sid]
            require(step["proof"] == proof, "Artifact replay cannot prove a runtime journey step")
            claims.update(step["acceptance"])
        require(set(case["acceptance"]) <= claims, "Scenario acceptance must match the steps it actually observes")
        witnessed.update(ids)
    require(witnessed == set(by_id), "Journey has untested steps; keep runtime/permission gaps pending instead of removing them")


def valid_check(workflow, state, run_id, name=None):
    receipt = next((r for r in state["runs"] if r["id"] == run_id), None)
    require(receipt and receipt["kind"] == "check" and receipt["status"] == "passed" and
            (name is None or receipt["name"] == name), "Case needs its actual successful configured check")
    require(receipt["fingerprint"] == vcs.fingerprint(workflow.root) and
            receipt["config_hash"] == state["execution_hash"] and
            receipt["cwd"] == str(workflow.root), "Case check is stale or belongs to another checkout")
    require(not any(r["kind"] == "check" and r["name"] == receipt["name"] and r["status"] == "failed"
                    for r in state["runs"][state["runs"].index(receipt) + 1:]), "A newer failed check supersedes case evidence")
    verify_snapshots(workflow.root, receipt["evidence"])
    from .reuse import validate_receipt
    validate_receipt(workflow, state, receipt)
    return receipt


def cases(workflow, state):
    if not enabled(state) or state["stages"]["intake"]["status"] != "done":
        return []
    return workflow.report_for(state, "intake")["details"]["scenarios"]


def latest(workflow, state):
    epoch = state["stages"]["intake"]["epoch"]
    return {r["case"]: r for r in state.get("case_results", []) if r["intake_epoch"] == epoch}


def result_status(workflow, state, case, result, code):
    if result is None:
        return "pending"
    try:
        verify_snapshots(workflow.root, result["evidence"])
        if result["status"] != "waived":
            require(result["fingerprint"] == code and result["config_hash"] == state["execution_hash"], "Code changed")
        if result["status"] == "passed" and case["executor"] == "command":
            valid_check(workflow, state, result["check"], case["check"])
    except (HarnessError, KeyError, ValueError):
        return "stale"
    return result["status"]


def progress(workflow, state):
    try:
        definitions = cases(workflow, state)
    except (HarnessError, KeyError, TypeError) as error:
        return {"total": 0, "remaining": None, "status": "unavailable", "error": str(error), "cases": []}
    records, code = latest(workflow, state), vcs.fingerprint(workflow.root)
    items = [{"id": c["id"], "executor": c["executor"], "level": c["level"],
              "batch": c.get("batch"), "status": result_status(workflow, state, c, records.get(c["id"]), code)}
             for c in definitions]
    counts = dict.fromkeys(("pending", "passed", "failed", "blocked", "waived", "stale"), 0)
    counts.update(Counter(i["status"] for i in items))
    remaining = [i for i in items if i["status"] not in {"passed", "waived"}]
    return {"total": len(items), **counts, "remaining": len(remaining),
            "human_remaining": sum(i["executor"] == "human" for i in remaining),
            "human_batches": sorted({i["batch"] for i in remaining if i["executor"] == "human"}),
            "cases": (remaining + [i for i in items if i["status"] in {"passed", "waived"}])[:20],
            "cases_omitted": max(0, len(items) - 20)}


def record(workflow, source):
    body = read_json(inside(workflow.root, source))
    return record_body(workflow, body)


def record_body(workflow, body):
    with file_lock(workflow.lock_path):
        state = workflow.load()
        # A newly observed failure can invalidate a completed review; retain that failure
        # even then. Positive outcomes still require the normal reopen/repair path.
        if body.get("status") not in {"failed", "blocked"}:
            workflow.consistent(state)
        require(not any(r["status"] in {"running", "unresolved"} for r in state["runs"]), "Resolve active commands first")
        case = next((c for c in cases(workflow, state) if c["id"] == body.get("case")), None)
        require(case, "Unknown case in the current Codex intake")
        from .engine import current
        require(current(state) in {"implement", "review", "integration"} or
                (current(state) is None and body.get("status") in {"failed", "blocked"}),
                "Record cases during implementation or verification (post-delivery failures remain recordable)")
        status = body.get("status")
        require(status in {"passed", "failed", "blocked", "waived"}, "Invalid case status")
        nonempty(body.get("summary"), "case result.summary")
        evidence = snapshots(workflow.root, strings(body.get("artifacts"), "case result.artifacts"))
        if status == "waived" or (status == "passed" and case["executor"] == "human"):
            require(body.get("actor") == "user", "Human outcomes/waivers need the actual user decision")
            nonempty(body.get("authorization"), "case result.authorization (quote actual user response)")
        if status == "passed" and case["executor"] == "command":
            receipt = valid_check(workflow, state, body.get("check"), case["check"])
            require(receipt["stage"] in {"implement", "review", "integration"}, "Feasibility is not final product verification")
            evidence.extend(receipt["evidence"])
        result = {"id": uuid.uuid4().hex, "case": case["id"], "status": status,
                  "summary": body["summary"], "check": body.get("check"), "actor": body.get("actor", "codex"),
                  "authorization": body.get("authorization"), "evidence": evidence,
                  "intake_epoch": state["stages"]["intake"]["epoch"], "at": now(),
                  "fingerprint": vcs.fingerprint(workflow.root), "config_hash": state["execution_hash"]}
        state.setdefault("case_results", []).append(result)
        workflow.save(state, "case_recorded", case=case["id"], status=status)
        return progress(workflow, state)


def closure(workflow, state):
    result = progress(workflow, state)
    require(result["total"] and result["remaining"] == 0,
            f"Acceptance incomplete: {result['remaining']} case(s) pending/failed/blocked/stale; inspect test-progress")
    # Pin all product/manual evidence in the final review, including explicit exclusions.
    return [e["path"] for r in latest(workflow, state).values() for e in r["evidence"]]
