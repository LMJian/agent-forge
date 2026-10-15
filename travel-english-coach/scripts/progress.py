#!/usr/bin/env python3
"""Small local learning ledger. Python standard library, macOS/Linux."""

import argparse
import copy
from datetime import date, datetime, timedelta
import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile


RATINGS = {"独立完成", "需要提示", "需要重练", "未评估"}
PROFILE_FIELDS = {"goal", "destination", "departure_date", "daily_minutes", "days_per_week", "plan_months"}
PROGRESS_FIELDS = {"phase", "level_note", "next_lesson", "next_assessment_date", "assessment", "notes"}
SESSION_FIELDS = {"id", "date", "status", "topic", "mode", "minutes", "summary", "abilities", "next_step"}
ITEM_FIELDS = {"id", "phrase", "meaning", "issue", "next_review", "attempts", "last_result"}
REVIEW_METADATA = {"last_reviewed_on", "interval_days", "last_evidence", "last_mode"}
ITEM_EDIT_FIELDS = {"id", "phrase", "meaning", "issue", "next_review"}
MODES = {"text", "voice", "mixed"}
REVIEW_INTERVALS = (1, 3, 7, 14)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def valid_date(value, nullable=False):
    if value is None and nullable:
        return
    require(isinstance(value, str), "Date must be an ISO date string")
    require(date.fromisoformat(value).isoformat() == value, "Use YYYY-MM-DD dates")


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def bounded_int(value, low, high):
    return type(value) is int and low <= value <= high


def fields(obj, allowed):
    require(isinstance(obj, dict), "Expected a JSON object")
    require(not set(obj) - allowed, "Unknown fields: " + ", ".join(sorted(set(obj) - allowed)))


def validate_abilities(abilities):
    require(isinstance(abilities, dict), "Abilities/assessment must be an object")
    for task, rating in abilities.items():
        require(nonempty(task), "Ability name cannot be empty")
        fields(rating, {"status", "evidence"})
        require(rating.get("status") in RATINGS, "Invalid ability status")
        require(nonempty(rating.get("evidence")), "Ability needs observed evidence or reason it is unassessed")


def merge_abilities(existing, updates):
    require(isinstance(updates, dict), "Ability update must be an object")
    merged = copy.deepcopy(existing)
    for task, rating in updates.items():
        require(nonempty(task), "Ability name cannot be empty")
        if rating is None:
            merged.pop(task, None)
        else:
            validate_abilities({task: rating})
            merged[task] = copy.deepcopy(rating)
    return merged


def valid_timestamp(value):
    require(isinstance(value, str), "Timestamp must be a string")
    require(datetime.fromisoformat(value).utcoffset() is not None, "Timestamp needs a timezone")


def validate_profile(profile):
    fields(profile, PROFILE_FIELDS | {"foundation"})
    require(profile.get("foundation") == "英语基础薄弱", "Invalid foundation description")
    require(nonempty(profile.get("goal")), "Goal cannot be empty")
    require(profile["destination"] is None or nonempty(profile["destination"]), "Invalid destination")
    valid_date(profile["departure_date"], nullable=True)
    for key, high in (("daily_minutes", 1440), ("days_per_week", 7), ("plan_months", 120)):
        require(bounded_int(profile.get(key), 1, high), "Invalid " + key)


def validate_progress(progress):
    fields(progress, PROGRESS_FIELDS)
    require(progress.get("phase") in {"基础", "常见任务", "综合应用"}, "Invalid phase")
    for key in ("level_note", "next_lesson", "notes"):
        require(isinstance(progress.get(key), str), "Invalid progress " + key)
    valid_date(progress["next_assessment_date"], nullable=True)
    validate_abilities(progress.get("assessment"))


def validate_session(session, sid):
    fields(session, SESSION_FIELDS | {"updated_at"})
    require(nonempty(sid) and session.get("id") == sid, "Session ID does not match its key")
    valid_date(session.get("date"))
    valid_timestamp(session.get("updated_at"))
    require(session.get("status") in {"in_progress", "completed"}, "Invalid session status")
    require(session.get("mode") in MODES, "Invalid session mode")
    require(nonempty(session.get("topic")), "Session topic is required")
    require(session["minutes"] is None or bounded_int(session["minutes"], 0, 1440), "Invalid actual minutes")
    for key in ("summary", "next_step"):
        require(isinstance(session.get(key), str), "Invalid session " + key)
    validate_abilities(session.get("abilities"))


def validate_item(item, iid):
    fields(item, ITEM_FIELDS | REVIEW_METADATA)
    require(nonempty(iid) and item.get("id") == iid, "Review item ID does not match its key")
    for key in ("phrase", "meaning"):
        require(nonempty(item.get(key)), "Review item requires " + key)
    require(isinstance(item.get("issue"), str), "Invalid review issue")
    valid_date(item.get("next_review"))
    require(bounded_int(item.get("attempts"), 0, sys.maxsize), "Invalid review attempts")
    require(item.get("last_result") in RATINGS, "Invalid review result")
    # Legacy v1 records have none of these fields. Do not invent past review dates.
    present = REVIEW_METADATA & set(item)
    if present:
        require(present == REVIEW_METADATA, "Incomplete review scheduling metadata")
        valid_date(item["last_reviewed_on"])
        require(bounded_int(item["interval_days"], 1, 36500), "Invalid review interval")
        require(item["attempts"] > 0 and item["last_result"] != "未评估", "Review metadata requires an observed result")
        require(nonempty(item["last_evidence"]), "Review result needs evidence")
        require(item["last_mode"] in MODES, "Invalid review mode")
        require((date.fromisoformat(item["next_review"]) - date.fromisoformat(item["last_reviewed_on"])).days
                == item["interval_days"], "Review date does not match its interval")


def validate_state(state):
    fields(state, {"schema_version", "revision", "updated_at", "profile", "progress", "sessions", "review_items"})
    require(type(state.get("schema_version")) is int and state["schema_version"] == 1,
            "Unsupported schema version; do not reset existing state")
    require(bounded_int(state.get("revision"), 0, sys.maxsize), "Invalid state revision")
    valid_timestamp(state.get("updated_at"))
    validate_profile(state.get("profile"))
    validate_progress(state.get("progress"))
    for key, validator in (("sessions", validate_session), ("review_items", validate_item)):
        require(isinstance(state.get(key), dict), "Invalid state field: " + key)
        for identifier, entry in state[key].items():
            validator(entry, identifier)


def new_state():
    return {
        "schema_version": 1,
        "revision": 0,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "profile": {
            "foundation": "英语基础薄弱",
            "goal": "用简单自然的英语独立处理常见旅行事务，并能主动澄清和求助",
            "destination": None,
            "departure_date": None,
            "daily_minutes": 60,
            "days_per_week": 6,
            "plan_months": 6,
        },
        "progress": {
            "phase": "基础",
            "level_note": "尚未测评；听力、口语和发音能力均未验证",
            "next_lesson": "了解出行时间，再通过简单问题确认表达基础，开始首个旅行场景",
            "next_assessment_date": None,
            "assessment": {},
            "notes": "尚未开始实际练习；前两周可按每天30分钟适应",
        },
        "sessions": {},
        "review_items": {},
    }


def read_state(path):
    state = json.loads(path.read_text(encoding="utf-8"))
    validate_state(state)
    return state


def atomic_json(path, value):
    fd, name = tempfile.mkstemp(prefix=".progress-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def merge_patch(state, patch):
    validate_state(state)
    fields(patch, {"profile", "progress", "session", "review_items", "review_results"})
    require(bool(patch), "Empty update")
    out = copy.deepcopy(state)
    if "profile" in patch:
        fields(patch["profile"], PROFILE_FIELDS)
        out["profile"].update(patch["profile"])
    if "progress" in patch:
        update = patch["progress"]
        fields(update, PROGRESS_FIELDS)
        for key, value in update.items():
            out["progress"][key] = (merge_abilities(out["progress"][key], value)
                                    if key == "assessment" else copy.deepcopy(value))

    if "session" in patch:
        update = patch["session"]
        fields(update, SESSION_FIELDS)
        sid = update.get("id")
        require(nonempty(sid), "Session ID is required")
        session = out["sessions"].get(sid, {"minutes": None, "summary": "", "abilities": {}, "next_step": ""})
        # Preserve other observed abilities when adding a new scenario checkpoint.
        abilities = merge_abilities(session["abilities"], update.get("abilities", {}))
        session.update(update)
        session["abilities"] = abilities
        session["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        out["sessions"][sid] = session

    if "review_items" in patch:
        require(isinstance(patch["review_items"], list), "Review items must be an array")
        seen = set()
        for update in patch["review_items"]:
            fields(update, ITEM_EDIT_FIELDS)
            iid = update.get("id")
            require(nonempty(iid), "Review item ID is required")
            require(iid not in seen, "Duplicate review item ID in update")
            seen.add(iid)
            item = out["review_items"].get(iid, {"attempts": 0, "last_result": "未评估", "issue": ""})
            item.update(update)
            if "next_review" in update and "last_reviewed_on" in item:
                valid_date(update["next_review"])
                item["interval_days"] = (date.fromisoformat(update["next_review"]) -
                                         date.fromisoformat(item["last_reviewed_on"])).days
            out["review_items"][iid] = item
    if "review_results" in patch:
        apply_review_results(out, patch["review_results"])
    out["revision"] += 1
    out["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    validate_state(out)
    return out


def apply_review_results(state, results):
    require(isinstance(results, list), "Review results must be an array")
    seen = set()
    for result in results:
        fields(result, {"id", "reviewed_on", "result", "evidence", "mode"})
        iid = result.get("id")
        require(nonempty(iid), "Review result needs an item ID")
        require(iid not in seen, "Duplicate review result for the same item")
        seen.add(iid)
        require(iid in state["review_items"], "Unknown review item: " + iid)
        valid_date(result.get("reviewed_on"))
        require(result.get("result") in RATINGS - {"未评估"}, "Review result must be observed")
        require(nonempty(result.get("evidence")), "Review result needs evidence")
        require(result.get("mode") in MODES, "Invalid review mode")
        item = state["review_items"][iid]
        if "last_reviewed_on" in item:
            require(result["reviewed_on"] >= item["last_reviewed_on"], "Review predates the last recorded review")
        previous = item.get("interval_days", 0)
        interval = (next((step for step in REVIEW_INTERVALS if step > previous), previous or 1)
                    if result["result"] == "独立完成" else 1)
        if result["result"] == "独立完成" and result["reviewed_on"] == item.get("last_reviewed_on"):
            interval = previous
        reviewed = date.fromisoformat(result["reviewed_on"])
        item.update({"attempts": item["attempts"] + 1, "last_result": result["result"],
                     "last_reviewed_on": result["reviewed_on"], "interval_days": interval,
                     "last_evidence": result["evidence"], "last_mode": result["mode"],
                     "next_review": (reviewed + timedelta(days=interval)).isoformat()})


def ordered_sessions(state):
    return sorted(state["sessions"].values(),
                  key=lambda s: (s["date"], s["updated_at"], s["id"]), reverse=True)


def snapshot(state, path, today, limit):
    sessions = ordered_sessions(state)
    completed = [s for s in sessions if s["status"] == "completed"]
    due = sorted((i for i in state["review_items"].values() if i["next_review"] <= today), key=lambda i: (i["next_review"], i["id"]))
    return {
        "status": "ready", "data_file": str(path),
        "revision": state["revision"], "updated_at": state["updated_at"],
        "profile": state["profile"], "progress": state["progress"],
        "completed_sessions": len(completed),
        "in_progress_sessions": sum(s["status"] == "in_progress" for s in sessions),
        "unfinished_sessions": [s for s in sessions if s["status"] == "in_progress"][:min(3, limit)],
        "known_completed_minutes": sum(s["minutes"] for s in completed if s["minutes"] is not None),
        "completed_sessions_without_duration": sum(s["minutes"] is None for s in completed),
        "recent_sessions": sessions[:min(3, limit)] if limit == 10 else sessions[:limit],
        "due_review_items": due[:limit], "due_review_count": len(due),
        "total_review_items": len(state["review_items"]),
    }


def query_records(state, path, args):
    base = {"status": "ready", "data_file": str(path), "revision": state["revision"]}
    if args.command == "get":
        collection = state["sessions" if args.kind == "session" else "review_items"]
        require(args.id in collection, "Record not found: " + args.id)
        return {**base, "kind": args.kind, "item": collection[args.id]}
    require(1 <= args.limit <= 50 and args.offset >= 0, "Limit must be 1..50 and offset nonnegative")
    if args.command == "sessions":
        items = [s for s in ordered_sessions(state) if args.status == "all" or s["status"] == args.status]
    else:
        valid_date(args.today)
        query = args.query.casefold().strip()
        items = sorted((i for i in state["review_items"].values()
                        if (not args.due or i["next_review"] <= args.today)
                        and (not query or any(query in i[k].casefold() for k in ("id", "phrase", "meaning", "issue")))),
                       key=lambda i: (i["next_review"], i["id"]))
    end = args.offset + args.limit
    return {**base, "items": items[args.offset:end], "total": len(items), "offset": args.offset,
            "next_offset": end if end < len(items) else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", help="Override fixed data directory, mainly for isolated tests")
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("show")
    show.add_argument("--today", default=date.today().isoformat())
    show.add_argument("--limit", type=int, default=10)
    get = sub.add_parser("get", help="Read one session or review item by ID")
    get.add_argument("kind", choices=("session", "review"))
    get.add_argument("id")
    sessions = sub.add_parser("sessions", help="List sessions, including older unfinished lessons")
    sessions.add_argument("--status", choices=("all", "in_progress", "completed"), default="all")
    reviews = sub.add_parser("reviews", help="Search all review items, including items not yet due")
    reviews.add_argument("--query", default="")
    reviews.add_argument("--due", action="store_true")
    reviews.add_argument("--today", default=date.today().isoformat())
    for command in (sessions, reviews):
        command.add_argument("--limit", type=int, default=10)
        command.add_argument("--offset", type=int, default=0)
    sub.add_parser("init")
    save = sub.add_parser("save")
    save.add_argument("--file", required=True)
    save.add_argument("--expected-revision", type=int, required=True)
    args = parser.parse_args()
    if args.data_dir:
        data_dir = Path(args.data_dir).expanduser().resolve()
    else:
        config_path = Path(__file__).resolve().parents[1] / "settings.json"
        configured = json.loads(config_path.read_text(encoding="utf-8"))["data_dir"]
        data_dir = Path(configured).expanduser()
        require(data_dir.is_absolute(), "Configured data_dir must be absolute")
    path = data_dir / "progress.json"

    if args.command in {"show", "get", "sessions", "reviews"}:
        if args.command == "show":
            valid_date(args.today)
            require(1 <= args.limit <= 50, "Limit must be 1..50")
        if not path.exists():
            return {"status": "not_initialized", "data_file": str(path)}
        state = read_state(path)
        return (snapshot(state, path, args.today, args.limit) if args.command == "show"
                else query_records(state, path, args))

    # Read and validate input before opening the data directory.
    patch = json.loads(Path(args.file).read_text(encoding="utf-8")) if args.command == "save" else None
    if args.command == "save":
        require(path.exists(), "No learning record; initialize it first")
    data_dir.mkdir(parents=True, exist_ok=True)
    with (data_dir / ".progress.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if args.command == "init":
            if not path.exists():
                atomic_json(path, new_state())
            return snapshot(read_state(path), path, date.today().isoformat(), 10)
        state = read_state(path)
        require(state["revision"] == args.expected_revision,
                "Revision conflict: expected %s, current %s; reload and merge" % (args.expected_revision, state["revision"]))
        updated = merge_patch(state, patch)
        atomic_json(data_dir / "progress.previous.json", state)
        atomic_json(path, updated)
        return {"status": "saved", "revision": updated["revision"], "data_file": str(path),
                "session_count": len(updated["sessions"]), "review_item_count": len(updated["review_items"])}


if __name__ == "__main__":
    try:
        print(json.dumps(main(), ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
