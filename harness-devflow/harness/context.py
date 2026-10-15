"""Stage-specific references with content IDs; acknowledging reads never validates work."""
from .engine import current, stage_order
from .model import digest, require
from .storage import file_lock


DEPENDENCIES = {
    "intake": (), "design": ("intake",), "design_audit": ("intake", "design"),
    "test_design": ("intake", "design", "design_audit"), "design_approval": ("design", "design_audit", "test_design"),
    "interfaces": ("intake", "design", "test_design"), "plan": ("intake", "design", "test_design", "interfaces"),
    "implement": ("intake", "plan", "design", "test_design", "interfaces"),
    "review": ("intake", "plan", "design", "test_design", "implement"),
    "integration": ("intake", "test_design", "review", "push"),
    "push": ("review", "integration"), "pr": ("intake", "review", "integration", "push"),
    "monitor": ("pr",), "release": ("review", "integration", "monitor"),
    "deploy": ("release", "push", "pr"), "knowledge": ("intake", "design", "review", "integration", "deploy"),
}


def references(workflow, state, *, all_inputs=False, module=None):
    stage = current(state)
    wanted = set(DEPENDENCIES.get(stage, ()))
    result = []
    for name in stage_order(state):
        item = state["stages"][name]
        if not item.get("report") or not (all_inputs or name in wanted):
            continue
        report = workflow.report_for(state, name)
        artifacts = report["artifacts"]
        if name == "design" and module is not None:
            designs = report.get("details", {}).get("designs", {})
            artifacts = [designs[module]] if module in designs else artifacts
        # Current bytes still undergo normal stale checks; this ID describes accepted evidence.
        content_id = digest({"epoch": item["epoch"], "evidence": item.get("evidence", []), "artifacts": artifacts})
        previous = state.get("context_reads", {}).get(name)
        result.append({"stage": name, "report": item["report"], "artifacts": artifacts,
                       "content_id": content_id, "read_status": "unchanged" if previous == content_id else
                       ("changed" if previous else "unread")})
    return result


def acknowledge(workflow, content_id):
    with file_lock(workflow.lock_path):
        state = workflow.load()
        workflow.consistent(state)
        # Include module-filtered design references as well as the complete history view.
        candidates = references(workflow, state, all_inputs=True)
        for module in state["modules"]:
            candidates.extend(references(workflow, state, module=module))
        item = next((r for r in candidates if r["content_id"] == content_id), None)
        require(item, "Unknown or changed context ID; read the current reference before acknowledging it")
        state.setdefault("context_reads", {})[item["stage"]] = content_id
        workflow.save(state, "context_read", stage=item["stage"], content_id=content_id)
        return {"stage": item["stage"], "read_status": "unchanged", "content_id": content_id}
