#!/usr/bin/env python3
"""Local artifact consistency checks. Never calls Lark or grants authorization."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid

# Also support importlib-based offline tests and consumers.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))


STAGES = {"proposed": "proposal", "decided": "decision",
          "implemented": "implementation", "operating": "runtime", "unknown": None}
SUPPORT = {"proposal", "decision", "implementation", "runtime", "context"}
STATUSES = {"inflight", "unknown", "submitted", "succeeded", "failed"}


def initial_state(topic, *, document=False, html=False, publish=False, read_only=False):
    if read_only and (document or publish):
        raise ValueError("read_only forbids remote document creation and publication")
    run = {
        "schema_version": 2, "run_id": uuid.uuid4().hex[:12], "topic": topic,
        "created_at": datetime.now(timezone.utc).isoformat(), "identity": "user",
        "delivery": {"document": document, "html": html or publish,
                     "publish": publish, "read_only": read_only},
        "limits": {"collection": {"calls": 40, "seconds": 600},
                   "delivery": {"calls": 15, "seconds": 300},
                   "total": {"calls": 55, "seconds": 900}},
        "active_seconds": {"collection": 0, "delivery": 0},
        "budget_changes": [], "calls": [], "rounds": [], "pending_leads": [],
        "coverage": {}, "operations": {"document": [], "app": [], "publish": []},
        "artifacts": {},
    }
    run.update(budget_policy="default", clock={"segments": [], "running": None},
               probes={}, questions=[], repositories=[])
    return run, {"schema_version": 2, "sources": [], "claims": []}


def budget_status(run, phase):
    counts = Counter(c["phase"] for c in run["calls"])
    limits, seconds = run["limits"], active_seconds(run)
    if (len(run["calls"]) >= limits["total"]["calls"] or
            sum(seconds.values()) >= limits["total"]["seconds"]):
        return "stop_total_budget"
    if counts[phase] >= limits[phase]["calls"] or seconds[phase] >= limits[phase]["seconds"]:
        return "stop_phase_budget"
    return "available"


def active_seconds(run, now=None):
    if run.get("schema_version") == 1:
        return run["active_seconds"]
    result = {"collection": 0.0, "delivery": 0.0}
    now = now or datetime.now(timezone.utc)
    for segment in run.get("clock", {}).get("segments", []):
        result[segment["phase"]] += (stamp(segment["ended_at"]) - stamp(segment["started_at"])).total_seconds()
    running = run.get("clock", {}).get("running")
    if running:
        result[running["phase"]] += (now - stamp(running["started_at"])).total_seconds()
    return result


def stamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp needs timezone")
    return result


def branch_status(run, branch):
    if budget_status(run, "collection") != "available":
        return "stop_budget"
    rounds = [r for r in run["rounds"] if r["branch"] == branch]
    gain = lambda r: any(r.get(k) for k in
                         ("new_claim_ids", "resolved_questions", "new_conflicts"))
    if (len(rounds) >= 2 and not any(gain(r) for r in rounds[-2:]) and
            branch not in run["pending_leads"]):
        return "pause_no_evidence_gain"
    return "continue_within_budget"


def validate(run, evidence):
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    require(run.get("schema_version") == evidence.get("schema_version") and run.get("schema_version") in (1, 2),
            "unsupported schema_version")
    require(run["identity"] == "user", "identity must be user")
    delivery = run["delivery"]
    for flag in ("document", "html", "publish", "read_only"):
        require(type(delivery[flag]) is bool, "delivery flags must be booleans")
    require(not delivery["publish"] or delivery["html"], "publish requires HTML")
    require(not delivery["read_only"] or not (delivery["document"] or delivery["publish"]),
            "read_only conflicts with remote outputs")
    for phase in ("collection", "delivery", "total"):
        for unit in ("calls", "seconds"):
            value = run["limits"][phase][unit]
            require(type(value) is int and value >= 0, "limits must be nonnegative integers")
    for phase in ("collection", "delivery"):
        value = run["active_seconds"][phase]
        require(type(value) in (int, float) and value >= 0, "active_seconds must be nonnegative")
    for call in run["calls"]:
        require(call["phase"] in ("collection", "delivery"), "invalid call phase")
        require(bool(call.get("command")) and bool(call.get("outcome")), "call needs command/outcome")

    sources, claims = evidence["sources"], evidence["claims"]
    source_map = {s["id"]: s for s in sources}
    claim_map = {c["id"]: c for c in claims}
    require(len(source_map) == len(sources), "duplicate source ID")
    require(len(claim_map) == len(claims), "duplicate claim ID")
    for s in sources:
        require(bool(s["id"]) and bool(s.get("locator")), "source needs ID and locator")
        require(s.get("access") in {"readable", "forbidden", "missing_scope", "not_found", "unsupported"},
                "invalid source access state")
        try:
            stamp = datetime.fromisoformat(s["observed_at"].replace("Z", "+00:00"))
            require(stamp.tzinfo is not None, "source observed_at needs timezone")
        except (KeyError, TypeError, ValueError, AttributeError):
            errors.append("source observed_at must be ISO timestamp")

    for c in claims:
        cid = c["id"]
        require(bool(cid) and bool(c.get("text")), "claim needs ID and text")
        require(c.get("status") in STAGES, f"{cid}: invalid status")
        require(type(c.get("current")) is bool, f"{cid}: current must be boolean")
        support = c.get("support", [])
        require(bool(support), f"{cid}: missing evidence")
        for item in support:
            source = source_map.get(item.get("source_id"))
            require(source is not None, f"{cid}: missing source")
            if source:
                require(source.get("access") == "readable", f"{cid}: unreadable source cannot support a claim")
            require(item.get("kind") in SUPPORT and bool(item.get("locator")),
                    f"{cid}: support needs kind and precise locator")
        needed = STAGES.get(c.get("status"))
        require(needed is None or any(s.get("kind") == needed for s in support),
                f"{cid}: status exceeds recorded evidence stage")
        for old in c.get("supersedes", []):
            require(old in claim_map and old != cid, f"{cid}: invalid supersedes reference")
            if old in claim_map:
                require(claim_map[old].get("current") is False, f"{old}: superseded claim is still current")
        for other in c.get("conflicts_with", []):
            require(other in claim_map and other != cid, f"{cid}: invalid conflict reference")
            if other in claim_map:
                require(cid in claim_map[other].get("conflicts_with", []), f"{cid}: conflict must be bidirectional")

    def visit(cid, trail):
        if cid in trail:
            return False
        return all(visit(old, trail | {cid}) for old in claim_map[cid].get("supersedes", [])
                   if old in claim_map)

    require(all(visit(cid, set()) for cid in claim_map), "cyclic supersedes relation")
    for round_ in run["rounds"]:
        require(bool(round_.get("branch")), "round needs branch")
        require(all(cid in claim_map for cid in round_.get("new_claim_ids", [])),
                "round references missing claim")

    for kind in ("document", "app", "publish"):
        attempts = run["operations"][kind]
        allowed = delivery["document"] if kind == "document" else delivery["publish"]
        require(not attempts or (allowed and not delivery["read_only"]), f"{kind}: remote operation outside delivery scope")
        require(len(attempts) <= 2, f"{kind}: retry limit exceeded")
        for index, attempt in enumerate(attempts):
            status = attempt["status"]
            require(status in STATUSES, f"{kind}: invalid operation status")
            require(bool(attempt.get("request_tag")), f"{kind}: missing request_tag")
            digest = attempt.get("content_sha256", "")
            require(len(digest) == 64 and all(x in "0123456789abcdef" for x in digest),
                    f"{kind}: missing/invalid content fingerprint")
            if index:
                previous = attempts[index - 1]
                require(previous["status"] == "failed" and previous.get("confirmed_not_applied") is True,
                        f"{kind}: previous attempt uncertain/applied; reconcile instead of resubmitting")
            receipt = attempt.get("receipt", {})
            if status == "submitted":
                require(kind == "publish" and bool(receipt.get("release_id")), "submitted publish needs release_id")
            if status == "succeeded":
                if kind in ("app", "document"):
                    require(bool(receipt.get("id")), f"{kind}: success needs server ID")
                if kind == "app":
                    require(str(receipt.get("id", "")).startswith("app_"), "invalid Miaoda app ID")
                if kind in ("publish", "document"):
                    require(str(receipt.get("url", "")).startswith(("https://", "http://")),
                            f"{kind}: success needs result URL")
    from record_validation import validate_details
    errors.extend(validate_details(run, evidence))
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("directory", type=Path)
    init.add_argument("--topic", required=True)
    for flag in ("document", "html", "publish", "read-only"):
        init.add_argument("--" + flag, action="store_true")
    check = sub.add_parser("check")
    check.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "init":
            run, evidence = initial_state(args.topic, document=args.document, html=args.html,
                                          publish=args.publish, read_only=args.read_only)
            args.directory.mkdir(parents=True, exist_ok=True)
            paths = [args.directory / name for name in ("run.json", "evidence.json")]
            if any(p.exists() for p in paths):
                raise ValueError("records already exist; resume instead of initializing")
            for path, value in zip(paths, (run, evidence)):
                with path.open("x", encoding="utf-8") as handle:
                    json.dump(value, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
            print("Initialized local task records; no external action performed.")
        else:
            run = json.loads((args.directory / "run.json").read_text())
            evidence = json.loads((args.directory / "evidence.json").read_text())
            from record_validation import assess
            result = assess(args.directory, run, evidence, validate)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result["record_valid"] and result["artifacts_valid"] else 1
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        print(f"Invalid/incomplete local records: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
