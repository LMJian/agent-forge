#!/usr/bin/env python3
"""Local ledger. Never launches Lark, authenticates, fetches Git, or renders a browser."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from check_artifacts import active_seconds, budget_status, stamp
from record_validation import context_key, digest, local_path


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    os.replace(temp, path)


@contextmanager
def ledger(root):
    with (root / ".ledger.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        run = json.loads((root / "run.json").read_text())
        if run.get("schema_version") != 2:
            raise ValueError("v1 is read-only legacy; start a new v2 directory, do not invent old receipts")
        yield run
        run["active_seconds"] = active_seconds(run)
        save(root / "run.json", run)


def clock(run, action, phase=None, reason=None):
    if action not in ("start", "pause", "resume"):
        raise ValueError("explicit clock action required")
    current = run["clock"]["running"]
    if action == "pause":
        if not current or not reason:
            raise ValueError("pause requires an active clock and reason")
        run["clock"]["segments"].append({**current, "ended_at": now(), "reason": reason})
        run["clock"]["running"] = None
    else:
        if current or phase not in ("collection", "delivery"):
            raise ValueError("pause before start/resume; supply phase")
        run["clock"]["running"] = {"phase": phase, "started_at": now()}
    return run["clock"]


def set_budget(run, plan):
    # A default plan may be selected once before any calls. Later increases need the user's instruction.
    authority = plan.get("authority")
    if authority not in ("default", "user") or not plan.get("reason"):
        raise ValueError("budget plan needs authority and reason")
    if authority == "default" and (run["calls"] or run["budget_changes"]):
        raise ValueError("default budget can only be planned once before collection")
    if authority == "user" and not plan.get("user_instruction"):
        raise ValueError("user budget change needs exact instruction or message locator")
    limits = plan["limits"]
    for phase in ("collection", "delivery", "total"):
        for unit in ("calls", "seconds"):
            if type(limits[phase][unit]) is not int or limits[phase][unit] < 0:
                raise ValueError("budget limits must be nonnegative integers")
    if any(limits["collection"][u] + limits["delivery"][u] > limits["total"][u] for u in ("calls", "seconds")):
        raise ValueError("phase allocations must fit total and preserve delivery reserve")
    run["budget_changes"].append({"at": now(), "previous": run["limits"], **plan})
    run["limits"] = limits
    run["budget_policy"] = "user_hard" if authority == "user" else "default"
    return {"limits": limits, "policy": run["budget_policy"]}


def prepare(root, run, request, probe=False):
    phase = request.get("phase", "collection")
    if phase not in ("collection", "delivery"):
        raise ValueError("invalid phase")
    if not run["clock"]["running"] or run["clock"]["running"]["phase"] != phase:
        raise ValueError("start/resume the correct phase clock before a call")
    if budget_status(run, phase) != "available":
        raise ValueError("budget exhausted; no new request reserved")
    argv = request.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(v, str) and v for v in argv):
        raise ValueError("supply complete argv array, not a label or shell command")
    if Path(argv[0]).name != "lark-cli" or "--as" not in argv or argv[argv.index("--as") + 1:] == [] or argv[argv.index("--as") + 1] != "user":
        raise ValueError("this recorder expects lark-cli argv with --as user")
    if len(argv) < 2 or argv[1] in ("auth", "config"):
        raise ValueError("do not record credentials or authentication workflows here")
    ctx = request.get("execution_context", {})
    if not all(isinstance(ctx.get(k), str) and ctx[k] for k in ("runner", "sandbox", "identity")) or ctx["identity"] != "user":
        raise ValueError("execution_context needs runner, sandbox, identity=user")
    key = context_key(ctx)
    if any(c["context_key"] == key and c.get("is_probe") and c["outcome"] == "pending" for c in run["calls"]):
        raise ValueError("wait for the single probe before parallel calls")
    if not probe and not run["probes"].get(key, {}).get("verified"):
        raise ValueError("new/unverified execution context: reserve one probe first")
    qids = request.get("question_ids", [])
    known = {q["id"] for q in run["questions"]}
    if (not probe and not qids) or any(q not in known for q in qids):
        raise ValueError("non-probe calls must name existing question_ids")
    if "--scope" in argv and argv[argv.index("--scope") + 1:][:1] == ["full"] and not request.get("full_read_reason"):
        raise ValueError("full document read requires full_read_reason; prefer section/keyword")
    if "docs" in argv and "+fetch" in argv and "--scope" not in argv:
        raise ValueError("explicit docs fetch scope required")
    discovery = probe and argv[1:3] == ["docs", "+search"]
    if discovery:
        if not request.get("discovery_reason") or "--page-all" in argv or any(
                c.get("is_discovery") and c["context_key"] == key for c in run["calls"]):
            raise ValueError("only one bounded discovery is allowed per context; reason required")
    elif probe and not (argv[1:3] == ["docs", "+fetch"] and "--scope" in argv and
                        argv[argv.index("--scope") + 1:][:1] == ["outline"]):
        raise ValueError("probe must be one docs +fetch --scope outline request")
    cid = "call-" + uuid.uuid4().hex[:16]
    folder = root / "calls" / cid
    folder.mkdir(parents=True)
    call = {"id": cid, "phase": phase, "argv": argv, "command": json.dumps(argv, ensure_ascii=False),
            "execution_context": ctx, "context_key": key, "is_probe": probe, "is_discovery": discovery,
            "discovery_reason": request.get("discovery_reason"), "question_ids": qids,
            "probe_call_id": None if probe else run["probes"][key]["call_id"],
            "started_at": now(), "outcome": "pending", "full_read_reason": request.get("full_read_reason")}
    run["calls"].append(call)
    return {"call_id": cid, "argv": argv, "capture_stdout": f"calls/{cid}/stdout.capture",
            "capture_stderr": f"calls/{cid}/stderr.capture", "instruction": "Execute natively using the recorded context; this tool has executed nothing."}


def context_failed(response, raw, stderr_raw):
    """Identify lost identity/connectivity without treating object-level 403 as logout."""
    if response.get("identity") not in (None, "user"):
        return True
    # Only inspect error metadata for JSON responses, not retrieved document text.
    fields = ("error", "errors", "message", "code", "status", "status_code", "http_status", "http_status_code")
    diagnostic = (json.dumps({k: response[k] for k in fields if k in response}) if response
                  else raw.decode("utf-8", errors="replace"))
    diagnostic = (diagnostic + "\n" + stderr_raw.decode("utf-8", errors="replace")).lower()
    return bool(re.search(
        r'\bunauthori[sz]ed\b|\bhttp(?:/\d(?:\.\d)?)?\s*[:=]?\s*401\b|'
        r'"(?:code|status|status_code|http_status|http_status_code)"\s*:\s*"?401\b|'
        r'keychain|invalid[ _]grant|(?:invalid|expired)[ _](?:access[ _])?token|'
        r'(?:access[ _])?token[ _](?:expired|invalid)|could not resolve|no such host|'
        r'name or service not known|temporary failure in name resolution|'
        r'connection (?:refused|reset|aborted)|failed to (?:connect|establish a new connection)|'
        r'network is unreachable|no route to host|timed?\s*out|timeout|'
        r'\b(?:econnrefused|econnreset|econnaborted|enetunreach|ehostunreach|etimedout|enotfound|eai_again)\b',
        diagnostic))


def finish(root, run, cid, stdout, stderr, exit_code):
    call = next((c for c in run["calls"] if c["id"] == cid), None)
    if not call or call["outcome"] != "pending":
        raise ValueError("unknown or already sealed call; retries need a new reservation")
    files = {"stdout": local_path(root, stdout), "stderr": local_path(root, stderr)}
    raw = files["stdout"].read_bytes()
    stderr_raw = files["stderr"].read_bytes()
    try:
        response = json.loads(raw)
        if not isinstance(response, dict):
            response = {}
    except (ValueError, UnicodeError):
        response = {}
    success = exit_code == 0 and response.get("ok") is True and response.get("identity") == "user"
    for stream, path in files.items():
        destination = root / "calls" / cid / (stream + ".raw")
        # Exclusive create plus hashes: never overwrite an earlier attempt's evidence.
        if destination.exists():
            if destination.read_bytes() != path.read_bytes():
                raise ValueError("sealed capture differs; do not replace previous evidence")
        else:
            with destination.open("xb") as out:
                out.write(path.read_bytes())
        call[stream] = {"path": str(destination.relative_to(root)), "sha256": digest(destination), "bytes": destination.stat().st_size}
    call.update(finished_at=now(), exit_code=exit_code, outcome="success" if success else "failed")
    lost_context = not success and context_failed(response, raw, stderr_raw)
    if call["is_probe"] or lost_context:
        run["probes"][call["context_key"]] = {"verified": success and not call.get("is_discovery"), "call_id": cid, "at": call["finished_at"]}
    data = response.get("data")
    doc = data.get("document") if isinstance(data, dict) else None
    doc = doc if isinstance(doc, dict) else {}
    call["response_summary"] = {"identity": response.get("identity"), "ok": response.get("ok"),
        "document_id": doc.get("document_id"), "revision": doc.get("revision_id"), "content_chars": len(doc.get("content") or "")}
    return {"call_id": cid, "outcome": call["outcome"], **call["response_summary"],
            "large_response": call["stdout"]["bytes"] > 16000,
            "next": "Read scoped excerpts, not the raw body." if success else "Inspect a bounded error excerpt; do not launch a batch on this context."}


def source(root, run, args):
    call = next(c for c in run["calls"] if c["id"] == args.call_id)
    if call["outcome"] != "success":
        raise ValueError("failed/pending call cannot supply readable factual evidence")
    evidence = json.loads((root / "evidence.json").read_text())
    if any(s["id"] == args.id for s in evidence["sources"]):
        raise ValueError("source ID exists; preserve old revision under its own ID")
    item = {"id": args.id, "kind": args.kind, "locator": args.locator, "access": "readable",
            "call_id": args.call_id, "fetched_at": call["finished_at"], "observed_at": call["finished_at"],
            "recorded_at": now(), "provenance": args.provenance, "scope": args.scope,
            "cache": call["stdout"]["path"], "sha256": call["stdout"]["sha256"]}
    if call["response_summary"].get("revision") is not None:
        item["revision"] = str(call["response_summary"]["revision"])
    evidence["sources"].append(item)
    save(root / "evidence.json", evidence)
    return item


def repository(run, rid, path, remote_result=None):
    if not rid or not path:
        raise ValueError("repository needs --id and --file path")
    path = path.resolve()
    def git(*argv):
        return subprocess.check_output(["git", "--no-optional-locks", "-C", str(path), *argv], text=True, timeout=15).strip()
    item = {"id": rid, "path": str(path), "head": git("rev-parse", "HEAD"),
            "branch": git("branch", "--show-current"), "dirty": bool(git("status", "--porcelain")),
            "observed_at": now()}
    if remote_result:
        lines = remote_result.read_text().strip().splitlines()
        if len(lines) != 1 or not re.fullmatch(r"[0-9a-f]{40,64}\s+refs/heads/[^\s]+", lines[0]):
            raise ValueError("remote result must contain exactly one ls-remote branch")
        item.update(remote_head=lines[0].split()[0], remote_ref=lines[0].split()[1],
                    remote_receipt=str(remote_result.resolve()), remote_receipt_sha256=digest(remote_result))
    same_branch = item.get("remote_ref") == "refs/heads/" + item["branch"]
    item["version_status"] = "unverified" if not item.get("remote_head") else ("matched" if same_branch and item["head"] == item["remote_head"] else "different")
    if any(r["id"] == rid for r in run["repositories"]):
        raise ValueError("repository snapshot ID exists; use a new ID to preserve history")
    run["repositories"].append(item)
    return item


def excerpt(root, filename, terms, cap=6000, max_hits=8):
    if not 1 <= cap <= 12000 or not 1 <= max_hits <= 20:
        raise ValueError("excerpt cap is 1..12000 characters, hits 1..20")
    raw = local_path(root, filename).read_text()
    try:
        data = json.loads(raw)
        inner = data.get("data") if isinstance(data, dict) else None
        doc = inner.get("document") if isinstance(inner, dict) else None
        text = doc.get("content") if isinstance(doc, dict) else None
        text = text if isinstance(text, str) else raw
    except ValueError:
        text = raw
    text = re.sub(r"</(?:p|h[1-6]|li|tr)>|<br\s*/?>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    matches = [(i, line) for i, line in enumerate(text.splitlines(), 1) if any(t.casefold() in line.casefold() for t in terms)]
    output = "\n".join(f"{i}: {line}" for i, line in matches[:max_hits])
    return {"file": filename, "terms": terms, "matches": len(matches), "truncated": len(output) > cap or len(matches) > max_hits, "excerpt": output[:cap]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["clock", "budget", "questions", "prepare", "finish", "source", "repository", "artifact", "mermaid", "excerpt", "status"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--file", type=Path)
    parser.add_argument("--phase", choices=["collection", "delivery"])
    parser.add_argument("--clock-action", choices=["start", "pause", "resume"])
    parser.add_argument("--reason")
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--call-id")
    parser.add_argument("--stdout")
    parser.add_argument("--stderr")
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--id")
    parser.add_argument("--kind", default="document")
    parser.add_argument("--locator")
    parser.add_argument("--scope")
    parser.add_argument("--provenance", choices=["primary", "secondary", "direct"], default="primary")
    parser.add_argument("--remote-result", type=Path)
    parser.add_argument("--mermaid-module", type=Path)
    parser.add_argument("--keyword", action="append")
    parser.add_argument("--max-chars", type=int, default=6000)
    args = parser.parse_args()
    root = args.directory.resolve()
    try:
        if args.action == "excerpt":
            if not args.file or not args.keyword:
                raise ValueError("excerpt requires --file and --keyword")
            result = excerpt(root, str(args.file), args.keyword, args.max_chars)
        else:
            with ledger(root) as run:
                if args.action == "clock":
                    result = clock(run, args.clock_action, args.phase, args.reason)
                elif args.action in ("budget", "prepare", "questions"):
                    data = json.loads(args.file.read_text())
                    if args.action == "budget":
                        result = set_budget(run, data)
                    elif args.action == "prepare":
                        result = prepare(root, run, data, args.probe)
                    else:
                        if not isinstance(data, list) or not data or len({q["id"] for q in data}) != len(data):
                            raise ValueError("questions must be nonempty with unique IDs")
                        referenced = {q for c in run["calls"] for q in c.get("question_ids", [])}
                        if not referenced <= {q["id"] for q in data}:
                            raise ValueError("cannot remove questions referenced by calls")
                        run["questions"] = data
                        result = {"questions": len(data)}
                elif args.action == "finish":
                    if args.exit_code is None:
                        raise ValueError("finish requires actual exit code")
                    result = finish(root, run, args.call_id, args.stdout, args.stderr, args.exit_code)
                elif args.action == "source":
                    if not all((args.id, args.locator, args.scope)):
                        raise ValueError("source needs ID, locator and actual read scope")
                    result = source(root, run, args)
                elif args.action == "repository":
                    result = repository(run, args.id, args.file, args.remote_result)
                elif args.action == "mermaid":
                    item = run["artifacts"][args.id]
                    path = local_path(root, item["path"])
                    parser_script = Path(__file__).with_name("check_mermaid.mjs")
                    if path.suffix != ".mmd":
                        raise ValueError("Mermaid validation expects a registered .mmd file")
                    if not args.mermaid_module:
                        item["mermaid"] = {"status": "not_checked", "reason": "No installed Mermaid parser supplied"}
                    else:
                        result = subprocess.run(["node", str(parser_script), str(args.mermaid_module.resolve()), str(path)],
                                                capture_output=True, text=True, timeout=30)
                        parsed = json.loads(result.stdout)
                        status = parsed.get("results", [{}])[0].get("status", "not_checked")
                        item["mermaid"] = {"status": status, "sha256": digest(path), "parser": str(args.mermaid_module.resolve()),
                                           "checked_at": now(), "detail": parsed}
                    result = item["mermaid"]
                elif args.action == "artifact":
                    if not args.id or not args.file:
                        raise ValueError("artifact needs ID and relative --file")
                    path = local_path(root, str(args.file))
                    if not path.is_file():
                        raise ValueError("artifact file missing")
                    item = {"path": str(args.file), "sha256": digest(path), "registered_at": now()}
                    run["artifacts"][args.id] = item
                    result = item
                else:
                    result = {"budget_status": {p: budget_status(run, p) for p in ("collection", "delivery")},
                              "active_seconds": active_seconds(run), "calls_reserved": len(run["calls"]),
                              "pending_calls": [c["id"] for c in run["calls"] if c["outcome"] == "pending"]}
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
