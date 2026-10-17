"""One bounded sequential check batch, with explicit deterministic evidence reuse."""
from . import runner
from .engine import current
from .model import HarnessError, require
from .reuse import reuse, validate_receipt
from .storage import verify_snapshots


def verify(workflow, module=None, fresh=False):
    state = workflow.load()
    stage = current(state)
    require(stage in {"implement", "review", "integration"}, "Verify during implementation or final verification")
    workflow.enter(stage)
    require((module is not None) == (stage == "implement"), "Implementation needs --module; final verification uses the owning checkout")
    names = state["config"]["stage_checks"].get("review" if module else stage, [])
    require(names, "Configure real verification commands first")
    results = []
    for name in names:
        receipt = None
        state = workflow.load()
        # Only an explicitly declared deterministic local check can avoid execution.
        # Keep original logs/timestamps; native/device/network checks execute freshly.
        if not fresh and module is None and state["config"]["checks"][name].get("reuse"):
            candidates = [r for r in reversed(state["runs"]) if r["kind"] == "check" and
                          r["name"] == name and r["status"] == "passed" and not r.get("reused_from")]
            for source in candidates:
                try:
                    validate_receipt(workflow, state, source)
                    verify_snapshots(workflow.root, source["evidence"])
                    receipt = reuse(workflow, name, source["id"])
                    break
                except HarnessError:
                    continue
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
