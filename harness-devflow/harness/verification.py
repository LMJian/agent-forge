"""One bounded sequential check batch, with explicit deterministic evidence reuse."""
from . import runner
from .engine import current
from .model import HarnessError, require
from .reuse import reuse, validate_source


def ordered_checks(state, module=None):
    stage = current(state)
    names = state["config"]["stage_checks"].get("review" if module else stage, [])
    tiers = {"critical": 0, "regression": 1, "packaging": 2}
    return sorted(names, key=lambda n: tiers[state["config"]["checks"][n].get("tier", "regression")])


def candidate(workflow, state, name, module=None):
    if not state["config"]["checks"][name].get("reuse"):
        return None, "No deterministic reuse policy"
    reason = "No original successful execution"
    for source in reversed(state["runs"]):
        if source["kind"] != "check" or source["name"] != name or source["status"] != "passed" or source.get("reused_from"):
            continue
        try:
            validate_source(workflow, state, name, source["id"], module=module)
            return source, "Identical declared inputs and unexpired evidence"
        except HarnessError as error:
            reason = str(error)
    return None, reason


def plan(workflow, module=None):
    state = workflow.load()
    stage = current(state)
    require(stage in {"implement", "review", "integration"}, "Plan verification during implementation or final verification")
    require((module is not None) == (stage == "implement"), "Implementation needs --module")
    from .quality import cases, progress
    definitions = cases(workflow, state)
    checks = []
    for name in ordered_checks(state, module):
        spec = state["config"]["checks"][name]
        previous = next((r for r in reversed(state["runs"]) if r["kind"] == "check" and r["name"] == name and not r.get("reused_from")), None)
        source, reason = candidate(workflow, state, name, module)
        checks.append({"name": name, "tier": spec.get("tier", "regression"), "proof": spec.get("proof", "component"),
                       "cases": [c["id"] for c in definitions if c.get("check") == name],
                       "reuse_from": source["id"] if source else None, "reuse_reason": reason,
                       "estimated_seconds": 0 if source else previous.get("duration_seconds") if previous else None})
    return {"checks": checks, "estimated_seconds": round(sum(c["estimated_seconds"] or 0 for c in checks), 3),
            "unknown_durations": sum(c["estimated_seconds"] is None for c in checks),
            "estimate_basis": "Last actual command durations; excludes unknown checks and manual/device work",
            "test_progress": progress(workflow, state)}


def verify(workflow, module=None, fresh=False):
    state = workflow.load()
    stage = current(state)
    require(stage in {"implement", "review", "integration"}, "Verify during implementation or final verification")
    workflow.enter(stage)
    require((module is not None) == (stage == "implement"), "Implementation needs --module; final verification uses the owning checkout")
    names = ordered_checks(state, module)
    require(names, "Configure real verification commands first")
    results = []
    for name in names:
        receipt = None
        state = workflow.load()
        # Only an explicitly declared deterministic local check can avoid execution.
        # Keep original logs/timestamps; native/device/network checks execute freshly.
        if not fresh:
            source, _ = candidate(workflow, state, name, module)
            if source:
                receipt = reuse(workflow, name, source["id"], module=module)
        if receipt is None:
            receipt = runner.run(workflow, "check", name, module=module)
        results.append({"name": name, "id": receipt["id"], "status": receipt["status"],
                        "reused_from": receipt.get("reused_from")})
        if receipt["status"] != "passed":
            if module is None and receipt["status"] == "failed":
                from .quality import cases, record_body
                for case in cases(workflow, workflow.load()):
                    if case["executor"] == "command" and case["check"] == name:
                        record_body(workflow, {"case": case["id"], "status": "failed", "check": receipt["id"],
                                             "summary": "Configured acceptance command failed",
                                             "artifacts": [e["path"] for e in receipt["evidence"]]})
            return {"status": receipt["status"], "checks": results, "remaining": names[len(results):]}
        if module is None:
            from .quality import cases, record_body
            for case in cases(workflow, workflow.load()):
                if case["executor"] == "command" and case["check"] == name:
                    record_body(workflow, {"case": case["id"], "status": "passed", "check": receipt["id"],
                                         "summary": "Configured acceptance command passed: " + case["expected"],
                                         "artifacts": [e["path"] for e in receipt["evidence"]]})
    return {"status": "passed", "checks": results, "remaining": [],
            "executed": sum(r["reused_from"] is None for r in results),
            "reused": sum(r["reused_from"] is not None for r in results)}
