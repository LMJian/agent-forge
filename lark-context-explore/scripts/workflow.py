"""Local workflow updates and receipt binding. Does not execute a remote command."""
import copy
import json
import uuid
from datetime import datetime, timezone

from record_validation import digest, local_path


DOMAINS = {"documents", "chats", "messages", "meetings", "prehistory", "decision_discussion"}
READS = {
    "docs": {"+search", "+fetch"},
    "im": {"+chat-search", "+messages-search", "+chat-messages-list", "+messages-mget",
           "+threads-messages-list", "+chat-members-list"},
    "minutes": {"+search", "+detail"}, "vc": {"+search", "+detail"},
    "calendar": {"+search-event"}, "wiki": {"+node-get"},
    "drive": {"+search", "+inspect"}, "contact": {"+search-user"},
    "sheets": {"+info", "+read", "+find"},
    "base": {"+base-get", "+table-list", "+table-get", "+field-list", "+field-get",
             "+record-list", "+record-get", "+record-search"},
    "apps": {"+access-scope-get", "+release-get"},
}


def write_kind(argv):
    return {("docs", "+create"): "document", ("apps", "+create"): "app",
            ("apps", "+html-publish"): "publish"}.get(tuple(argv[1:3]))


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def probe_key(context, argv):
    return context + ":" + argv[1]


def probe_allowed(argv):
    if len(argv) < 3 or "--page-all" in argv or "--transcript" in argv:
        return False
    if argv[1:4] in (["drive", "file.comments", "list"], ["drive", "file.comment.replys", "list"]):
        return True
    if argv[2] not in READS.get(argv[1], set()):
        return False
    if argv[1:3] == ["docs", "+fetch"]:
        return "--scope" in argv and argv[argv.index("--scope") + 1:][:1] in (
            ["outline"], ["section"], ["keyword"], ["range"])
    return True


def domain_matches(domain, call):
    argv = call.get("argv", [])
    if len(argv) < 3:
        return False
    if domain == "documents":
        return argv[1] in ("docs", "drive", "wiki", "sheets", "base")
    if domain == "chats":
        return argv[1] == "im" and argv[2] in ("+chat-search", "+chat-members-list")
    if domain == "messages":
        return argv[1] == "im" and argv[2] in READS["im"] - {"+chat-search", "+chat-members-list"}
    if domain == "meetings":
        return argv[1] in ("minutes", "vc", "calendar")
    return True  # History and rationale may be found in any primary source.


def collection_coverage(run):
    calls = {c["id"]: c for c in run["calls"]}
    errors, missing, gaps = [], [], []
    rows = run.get("coverage", {})
    if not isinstance(rows, dict):
        return {"complete": False, "missing": sorted(DOMAINS), "gaps": [], "errors": ["coverage must be an object"]}
    for domain, row in rows.items():
        if domain not in DOMAINS or not isinstance(row, dict):
            errors.append("unknown/invalid coverage row: " + domain)
            continue
        status = row.get("status")
        if status not in ("examined", "skipped", "partial", "blocked") or not row.get("reason"):
            errors.append(domain + ": coverage status/reason required")
        ids = row.get("call_ids", [])
        if status == "examined" and not ids:
            errors.append(domain + ": examined requires actual calls")
        for cid in ids:
            call = calls.get(cid, {})
            if not call or call.get("outcome") == "pending" or not domain_matches(domain, call):
                errors.append(domain + ": missing, pending or unrelated call " + cid)
            elif status == "examined" and call.get("outcome") != "success":
                errors.append(domain + ": failed query cannot prove examined coverage")
        if status in ("partial", "blocked"):
            gaps.append(domain)
    if run.get("coverage_scope", "targeted") == "full":
        missing = sorted(DOMAINS - rows.keys())
    return {"complete": not (errors or missing or gaps), "missing": missing, "gaps": gaps, "errors": errors}


def apply_updates(run, evidence, data):
    """Validate a whole batch before modifying either in-memory record."""
    from check_artifacts import validate
    if not isinstance(data, dict) or set(data) - {"questions", "sources", "claims", "coverage", "round", "pending_leads"}:
        raise ValueError("unknown batch update fields")
    candidate, facts = copy.deepcopy(run), copy.deepcopy(evidence)
    for field, owner in (("questions", candidate), ("sources", facts), ("claims", facts)):
        entries = data.get(field, [])
        if not isinstance(entries, list) or len({x["id"] for x in entries}) != len(entries):
            raise ValueError(field + " must have unique IDs")
        indexed = {x["id"]: x for x in owner[field]}
        for entry in entries:
            item = copy.deepcopy(entry)
            if field == "sources":
                if item["id"] in indexed:
                    raise ValueError("source ID exists; preserve its revision")
                call = next((c for c in candidate["calls"] if c["id"] == item.get("call_id")), {})
                if call.get("outcome") != "success":
                    raise ValueError("source needs successful finished call")
                item.update(access="readable", fetched_at=call["finished_at"], observed_at=call["finished_at"],
                            recorded_at=timestamp(), cache=call["stdout"]["path"], sha256=call["stdout"]["sha256"])
                item.setdefault("provenance", "primary")
                if call.get("response_summary", {}).get("revision") is not None:
                    item["revision"] = str(call["response_summary"]["revision"])
            indexed[item["id"]] = item
        owner[field] = list(indexed.values())
    if "coverage" in data:
        candidate["coverage"].update(data["coverage"])
    if "round" in data:
        candidate["rounds"].append(copy.deepcopy(data["round"]))
    if "pending_leads" in data:
        candidate["pending_leads"] = list(data["pending_leads"])
    errors = validate(candidate, facts) + collection_coverage(candidate)["errors"]
    if errors:
        raise ValueError("; ".join(errors[:5]))
    run.clear()
    run.update(candidate)
    evidence.clear()
    evidence.update(facts)
    return {key: len(data[key]) if isinstance(data[key], (list, dict)) else True for key in data}


def successful_call(root, run, cid, command, object_id=None):
    call = next((c for c in run["calls"] if c["id"] == cid), {})
    argv = call.get("argv", [])
    if call.get("outcome") != "success" or argv[1:1 + len(command)] != command:
        raise ValueError("operation needs matching successful native CLI call")
    if object_id and not any(object_id in arg for arg in argv[2:]):
        raise ValueError("readback call targets another object")
    path = local_path(root, call["stdout"]["path"])
    if digest(path) != call["stdout"]["sha256"]:
        raise ValueError("call receipt hash changed")
    response = json.loads(path.read_text())
    if response.get("ok") is not True or response.get("identity") != "user":
        raise ValueError("invalid raw operation receipt")
    return call, response


def values(value):
    if isinstance(value, dict):
        return [v for item in value.values() for v in values(item)]
    if isinstance(value, list):
        return [v for item in value for v in values(item)]
    return [str(value)]


def operation(root, run, data):
    kind, action = data.get("kind"), data.get("action")
    if kind not in ("document", "app", "publish"):
        raise ValueError("unknown operation kind")
    allowed = run["delivery"]["document"] if kind == "document" else run["delivery"]["publish"]
    if run["delivery"]["read_only"] or not allowed:
        raise ValueError("operation outside authorized delivery scope")
    attempts = run["operations"][kind]
    if action == "start":
        if len(attempts) >= 2 or (attempts and not (attempts[-1]["status"] == "failed" and attempts[-1].get("confirmed_not_applied"))):
            raise ValueError("reconcile existing operation; no uncertain/applied retry")
        ids = data.get("artifact_ids", [])
        if not ids:
            raise ValueError("bind the actual input artifacts before writing")
        bindings = {}
        for aid in ids:
            artifact = run["artifacts"][aid]
            path = local_path(root, artifact["path"])
            if digest(path) != artifact["sha256"]:
                raise ValueError("artifact changed; register current file first")
            bindings[aid] = artifact["sha256"]
        if kind == "publish":
            apps = run["operations"]["app"]
            if not apps or apps[-1]["status"] != "succeeded" or not apps[-1].get("verification"):
                raise ValueError("verify the created app's actual visibility before publishing")
        item = {"status": "inflight", "request_tag": uuid.uuid4().hex, "started_at": timestamp(),
                "content_sha256": bindings[ids[0]], "content_artifact": ids[0], "input_artifacts": bindings,
                "receipt": {}, "confirmed_not_applied": False}
        attempts.append(item)
    elif action == "result":
        if not attempts or attempts[-1]["status"] not in ("inflight", "unknown", "submitted"):
            raise ValueError("no unresolved operation to reconcile")
        item = attempts[-1]
        status = data["status"]
        if status not in ("unknown", "submitted", "succeeded", "failed"):
            raise ValueError("invalid result state")
        receipt = data.get("receipt", {})
        if status in ("succeeded", "submitted", "failed"):
            command = {"document": ["docs", "+create"], "app": ["apps", "+create"], "publish": ["apps", "+html-publish"]}[kind]
            reconciled = data.get("reconciled") is True
            if reconciled:
                if not data.get("reason"):
                    raise ValueError("reconciliation needs its matching reason")
                command = {"document": ["docs", "+fetch"], "app": ["apps", "+access-scope-get"], "publish": ["apps", "+release-get"]}[kind]
            elif item["status"] == "submitted" and kind == "publish":
                command = ["apps", "+release-get"]
            if status == "failed":
                call = next((c for c in run["calls"] if c["id"] == data.get("call_id")), {})
                if call.get("outcome") != "failed" or call.get("argv", [])[1:3] != command:
                    raise ValueError("failed operation needs matching failed call")
                if data.get("confirmed_not_applied") and not data.get("reason"):
                    raise ValueError("confirmed-not-applied needs reconciliation reason")
            else:
                release_id = item["receipt"].get("release_id") if command[-1] == "+release-get" else None
                call, response = successful_call(root, run, data.get("call_id"), command, release_id)
                if not reconciled and command[-1] != "+release-get" and call.get("operation_request_tag") != item["request_tag"]:
                    raise ValueError("call is not bound to this operation's input version")
                if reconciled:
                    target = receipt.get("id") or item["receipt"].get("release_id") or receipt.get("release_id")
                    if not target or not any(str(target) in arg for arg in call["argv"]):
                        raise ValueError("reconciliation must target the actual object/release")
                    checks = data.get("checks", [])
                    if not checks or not all(x in "\n".join(values(response.get("data"))) for x in checks):
                        raise ValueError("reconciliation content checks missing/failed")
                if not receipt or not all(str(v) in values(response.get("data")) for v in receipt.values()):
                    raise ValueError("IDs/URLs must come from this call's raw receipt")
                if kind in ("app", "document") and not receipt.get("id"):
                    raise ValueError("created object ID required")
                if kind in ("publish", "document") and status == "succeeded" and not receipt.get("url"):
                    raise ValueError("successful delivery URL required")
                if kind == "publish" and status == "submitted" and not receipt.get("release_id"):
                    raise ValueError("submitted publication needs release ID")
                if kind == "publish" and command[-1] == "+release-get" and "finished" not in values(response.get("data")):
                    raise ValueError("release is not finished")
                item["receipt_command"] = command
        item.update(status=status, receipt=receipt or item["receipt"], call_id=data.get("call_id"),
                    confirmed_not_applied=data.get("confirmed_not_applied", False), reason=data.get("reason"), updated_at=timestamp())
        if kind == "publish" and receipt.get("release_id"):
            item["release_id"] = receipt["release_id"]
    elif action == "verify":
        if not attempts or attempts[-1]["status"] != "succeeded" or kind == "publish":
            raise ValueError("verify a successful document or app")
        item = attempts[-1]
        command = ["docs", "+fetch"] if kind == "document" else ["apps", "+access-scope-get"]
        call, response = successful_call(root, run, data.get("call_id"), command, item["receipt"]["id"])
        checks = data.get("checks", [])
        content = "\n".join(values(response.get("data")))
        if not checks or not all(isinstance(x, str) and x and x in content for x in checks):
            raise ValueError("readback checks must match actual returned content")
        verification = {"call_id": call["id"], "checked_at": call["finished_at"],
                        "content_sha256": item["content_sha256"], "checks": checks}
        if kind == "document":
            revision = call.get("response_summary", {}).get("revision")
            if revision is None:
                raise ValueError("document readback must include its revision")
            verification["revision"] = str(revision)
        else:
            expected = run["delivery"].get("expected_visibility", "creator")
            actual = response
            locator = data.get("visibility_locator", "")
            for part in locator.split("."):
                actual = actual.get(part) if isinstance(actual, dict) else None
            if actual != expected or not actual or not locator:
                raise ValueError("actual visibility must match authorized audience with a response locator")
            verification.update(expected_visibility=expected, actual_visibility=actual,
                                visibility_locator=data["visibility_locator"])
        item["verification"] = verification
    else:
        raise ValueError("operation action must be start/result/verify")
    return copy.deepcopy(item)


def delivery_checks(root, run):
    missing = []
    for kind, attempts in run["operations"].items():
        if not attempts or attempts[-1]["status"] != "succeeded":
            continue
        item = attempts[-1]
        bindings = item.get("input_artifacts", {})
        if not bindings:
            missing.append(kind + ": legacy/unbound input; reconcile current version")
        for aid, sha in bindings.items():
            artifact = run["artifacts"].get(aid, {})
            try:
                matched = artifact.get("sha256") == sha == digest(local_path(root, artifact["path"]))
            except (KeyError, ValueError, OSError):
                matched = False
            if not matched:
                missing.append(kind + ": input artifact changed: " + aid)
        try:
            # Recheck recorded call and readback hashes, never trust a standalone succeeded flag.
            command = item.get("receipt_command") or {"document": ["docs", "+create"], "app": ["apps", "+create"], "publish": ["apps", "+html-publish"]}[kind]
            call = next((c for c in run["calls"] if c["id"] == item.get("call_id")), {})
            if kind == "publish" and call.get("argv", [])[1:3] == ["apps", "+release-get"]:
                command = ["apps", "+release-get"]
            _, response = successful_call(root, run, item.get("call_id"), command,
                                          item.get("release_id") if command[-1] == "+release-get" else None)
            if command[-1] in ("+create", "+html-publish") and call.get("operation_request_tag") != item.get("request_tag"):
                raise ValueError("call is not bound to this operation")
            if not all(str(v) in values(response.get("data")) for v in item["receipt"].values()):
                raise ValueError("remote receipt IDs/URLs changed")
            if kind in ("document", "app"):
                verify = item.get("verification", {})
                if verify.get("content_sha256") != item.get("content_sha256"):
                    raise ValueError("missing/current-version readback required")
                verify_command = ["docs", "+fetch"] if kind == "document" else ["apps", "+access-scope-get"]
                _, raw = successful_call(root, run, verify.get("call_id"), verify_command, item["receipt"]["id"])
                checks = verify.get("checks", [])
                if not checks or not all(x in "\n".join(values(raw.get("data"))) for x in checks):
                    raise ValueError("readback content checks missing/changed")
                if kind == "document" and not verify.get("revision"):
                    raise ValueError("readback revision required")
                if kind == "app" and (not verify.get("actual_visibility") or verify.get("actual_visibility") != verify.get("expected_visibility")):
                    raise ValueError("actual visibility not verified")
                if kind == "app":
                    actual = raw
                    for part in verify.get("visibility_locator", "").split("."):
                        actual = actual.get(part) if isinstance(actual, dict) else None
                    if actual != run["delivery"].get("expected_visibility", "creator"):
                        raise ValueError("visibility receipt does not match authorized audience")
        except (KeyError, ValueError, OSError, TypeError) as exc:
            missing.append(kind + ": " + str(exc))
    if run["delivery"]["publish"] and not any(x.get("status") == "succeeded" for x in run["operations"]["app"]):
        missing.append("publish: verified application receipt required")
    return missing
