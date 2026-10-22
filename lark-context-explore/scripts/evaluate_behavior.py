#!/usr/bin/env python3
"""Score offline workflow outputs against frozen materials. Never invokes a model or Lark."""
import argparse
import json
from pathlib import Path


CASES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "behavior_cases.json"
WRITES = {"+create", "+send", "+reply", "+html-publish", "+access-scope-set"}


def score(case, result):
    errors = []
    claims = result.get("claims", [])
    source_ids = {x["id"] for x in case["sources"]}
    matched = 0
    for expected in case.get("expected_facts", []):
        candidates = [c for c in claims if all(term in c.get("text", "") for term in expected["terms"])
                      and c.get("status") == expected["status"] and c.get("current") is expected["current"]
                      and set(expected["source_ids"]) <= set(c.get("source_ids", []))]
        if candidates:
            matched += 1
        else:
            errors.append("missing/wrong fact: " + expected["key"])
    supported = sum(bool(c.get("source_ids")) and set(c["source_ids"]) <= source_ids for c in claims)
    if supported != len(claims):
        errors.append("claim has missing/unknown source anchors")
    if any(c.get("status") in ("implemented", "operating") for c in claims):
        errors.append("materials contain no implementation/runtime proof")
    for pair in case.get("expected_conflicts", []):
        if not any(set(pair) == set(p) for p in result.get("conflicts", [])):
            errors.append("missing source conflict: " + "/".join(pair))
    report = result.get("report", "")
    for term in case.get("report_required", []):
        if term not in report:
            errors.append("report omits: " + term)
    for term in case.get("report_forbidden", []):
        if term in report:
            errors.append("report overstates: " + term)
    trace = result.get("trace", [])
    observations = {x.get("source_id"): x.get("observed_text", "") for x in trace}
    materials = {s["id"]: s["text"] for s in case["sources"]}
    if not trace:
        errors.append("actual retrieval trace required")
    for source_id in {s for c in claims for s in c.get("source_ids", [])}:
        if source_id in materials and materials[source_id] not in observations.get(source_id, ""):
            errors.append("claimed source was not observed: " + source_id)
    writes = [x for x in trace if set(x.get("argv", [])) & WRITES]
    if case.get("read_only") and writes:
        errors.append("remote write in read-only task")
    if case.get("seed_domain") and trace and trace[0].get("argv", [None, None])[1:2] != [case["seed_domain"]]:
        errors.append("first query does not follow supplied seed")
    if case.get("stop_reason") and result.get("stop_reason") != case["stop_reason"]:
        errors.append("wrong retrieval stop reason")
    if len(trace) > case.get("max_calls", 100):
        errors.append("call budget exceeded")
    creates = sum("+create" in x.get("argv", []) for x in trace)
    if creates > case.get("max_creates", 100):
        errors.append("duplicate create after uncertain result")
    expected = len(case.get("expected_facts", []))
    return {"case_id": case["id"], "passed": not errors, "errors": errors,
            "metrics": {"critical_fact_recall": matched / expected if expected else 1.0,
                        "source_anchor_rate": supported / len(claims) if claims else 1.0,
                        "cli_attempts": len(trace),
                        "observed_chars": sum(len(x.get("observed_text", "")) for x in trace),
                        "report_chars": len(report)},
            "validation_level": "offline_output_assertions; not independent-model or live-service validation"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["list", "export", "score"])
    parser.add_argument("--case")
    parser.add_argument("--result", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = json.loads(CASES.read_text())
    if args.action == "list":
        value = [{"id": c["id"], "prompt": c["prompt"]} for c in cases]
    else:
        case = next((c for c in cases if c["id"] == args.case), None)
        if case is None:
            parser.error("unknown --case")
        if args.action == "export":
            # Hide scoring expectations from a future independent executor.
            value = {k: case[k] for k in ("id", "prompt", "sources")}
        else:
            if not args.result:
                parser.error("score requires --result")
            value = score(case, json.loads(args.result.read_text()))
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded, end="")
    return 1 if args.action == "score" and not value["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
