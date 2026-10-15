"""Layered local checks; never executes a source command or contacts a service."""
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import unquote


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def is_digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def local_path(root, name):
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("recorded cache/artifact paths must stay inside task directory")
    path = (root / path).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("path escapes task directory")
    return path


def context_key(context):
    return hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()


def validate_details(run, evidence):
    from check_artifacts import stamp
    errors = []

    def need(ok, message):
        if not ok:
            errors.append(message)

    def time_ok(value):
        try:
            stamp(value)
            return True
        except (ValueError, TypeError, AttributeError):
            return False

    for name, artifact in run.get("artifacts", {}).items():
        need(bool(artifact.get("path")) and is_digest(artifact.get("sha256")), f"artifact {name}: path/hash required")
    for call in run.get("calls", []):
        if "observed_at" in call:
            need(time_ok(call["observed_at"]), "call observed_at invalid")
    if run.get("schema_version") == 1:
        return errors

    need(run.get("budget_policy") in ("default", "user_hard"), "invalid budget policy")
    need(isinstance(run.get("clock"), dict), "clock record required")
    current_time = datetime.now(timezone.utc)
    end = None
    for segment in run.get("clock", {}).get("segments", []):
        try:
            start, stop = stamp(segment["started_at"]), stamp(segment["ended_at"])
            need(stop >= start and (end is None or start >= end), "clock segments overlap or run backwards")
            need(stop <= current_time, "clock end is in the future")
            need(segment["phase"] in ("collection", "delivery") and bool(segment.get("reason")), "clock segment phase/reason required")
            end = stop
        except (KeyError, ValueError, TypeError, AttributeError):
            errors.append("invalid clock segment")
    running = run.get("clock", {}).get("running")
    if running:
        need(running.get("phase") in ("collection", "delivery") and time_ok(running.get("started_at")), "invalid running clock")
        if end and time_ok(running.get("started_at")):
            need(stamp(running["started_at"]) >= end, "running clock overlaps closed segment")
        if time_ok(running.get("started_at")):
            need(stamp(running["started_at"]) <= current_time, "running clock starts in the future")

    questions = {q.get("id"): q for q in run.get("questions", [])}
    claims = {c["id"]: c for c in evidence["claims"]}
    sources = {s["id"]: s for s in evidence["sources"]}
    repos = {r.get("id"): r for r in run.get("repositories", [])}
    need(len(questions) == len(run.get("questions", [])), "duplicate question IDs")
    need(len(repos) == len(run.get("repositories", [])), "duplicate repository IDs")
    for q in questions.values():
        need(bool(q.get("id")) and bool(q.get("text")), "question ID/text required")
        need(q.get("status") in ("answered", "partial", "unanswered"), "invalid question status")
        need(q.get("time_scope", "current") in ("current", "historical"), "invalid question time scope")
        need(set(q.get("requires", [])) <= {"document", "code", "runtime"}, "invalid question evidence tier")
        need(all(c in claims for c in q.get("claim_ids", [])), "question references missing claim")
        need(q.get("status") == "answered" or bool(q.get("gaps")), "partial/unanswered question needs gaps")
        if q.get("status") == "answered":
            need(bool(q.get("claim_ids")), "answered question needs claims")
    for repo in repos.values():
        need(bool(repo.get("path")) and bool(re.fullmatch(r"[0-9a-f]{40,64}", repo.get("head", ""))), "repository needs path/full commit")
        need(time_ok(repo.get("observed_at")), "repository observation time required")
    ids = set()
    calls = {c.get("id"): c for c in run["calls"]}
    for c in run["calls"]:
        cid = c.get("id")
        need(bool(cid) and cid not in ids, "missing/duplicate call ID")
        ids.add(cid)
        argv = c.get("argv")
        need(isinstance(argv, list) and len(argv) > 0 and all(isinstance(a, str) for a in argv), "call needs full argv array")
        ctx = c.get("execution_context", {})
        need(all(isinstance(ctx.get(k), str) and ctx[k] for k in ("runner", "sandbox", "identity")), "call execution context incomplete")
        need(ctx.get("identity") == "user", "call must retain user identity")
        need(c.get("context_key") == context_key(ctx), "execution context fingerprint mismatch")
        need(time_ok(c.get("started_at")), "call started_at required")
        need(c.get("outcome") in ("pending", "success", "failed"), "invalid call outcome")
        need(c.get("is_probe") or bool(c.get("question_ids")), "non-probe call must serve a question")
        need(all(q in questions for q in c.get("question_ids", [])), "call references missing question")
        if not c.get("is_probe"):
            probe = calls.get(c.get("probe_call_id"), {})
            need(probe.get("is_probe") and not probe.get("is_discovery") and probe.get("outcome") == "success" and
                 probe.get("context_key") == c.get("context_key"), "call needs successful probe in same execution context")
            if time_ok(probe.get("finished_at")) and time_ok(c.get("started_at")):
                need(stamp(c["started_at"]) >= stamp(probe["finished_at"]), "call began before probe completed")
        if c.get("outcome") != "pending":
            need(type(c.get("exit_code")) is int and time_ok(c.get("finished_at")), "finished call needs exit code/time")
            if time_ok(c.get("started_at")) and time_ok(c.get("finished_at")):
                need(stamp(c["finished_at"]) >= stamp(c["started_at"]), "call ends before start")
            for stream in ("stdout", "stderr"):
                data = c.get(stream, {})
                need(bool(data.get("path")) and is_digest(data.get("sha256")), "call output path/hash required")

    for s in sources.values():
        need(time_ok(s.get("fetched_at")) and time_ok(s.get("recorded_at")), f"{s['id']}: fetched_at/recorded_at required")
        if time_ok(s.get("fetched_at")) and time_ok(s.get("recorded_at")):
            need(stamp(s["recorded_at"]) >= stamp(s["fetched_at"]), "source recorded before fetched")
        need(s.get("provenance") in ("primary", "secondary", "direct"), "source provenance required")
        if s.get("kind") == "code":
            repo = repos.get(s.get("repository_id"))
            need(repo is not None and s.get("commit") == (repo or {}).get("head"), "code source must match repository snapshot")
            need(bool(s.get("file")) and type(s.get("line")) is int and s["line"] > 0 and is_digest(s.get("sha256")), "code source needs file/line/hash")
        elif s.get("access") == "readable" and s.get("kind") != "runtime":
            need(bool(s.get("call_id")), "readable Lark source needs call receipt")
        if s.get("call_id"):
            call = next((c for c in run["calls"] if c.get("id") == s["call_id"]), None)
            need(call is not None and call.get("outcome") != "pending", "source needs finished call")
            if s.get("access") == "readable":
                need(call is not None and call.get("outcome") == "success", "readable source needs successful call")
            if call:
                need(s.get("fetched_at") == call.get("finished_at"), "source fetch time must come from call receipt")
                need(s.get("cache") == call.get("stdout", {}).get("path") and
                     s.get("sha256") == call.get("stdout", {}).get("sha256"), "source cache must match call receipt")

    for c in claims.values():
        supports = [(x, sources.get(x["source_id"], {})) for x in c.get("support", [])]
        if c["status"] == "implemented":
            need(c.get("implementation_scope") in ("local_snapshot", "current_code"), "implemented claim needs explicit version scope")
            code = [s for support, s in supports if s.get("kind") == "code" and support.get("kind") == "implementation"]
            need(bool(code), "implemented claim needs code evidence")
            if c.get("implementation_scope") == "current_code":
                for s in code:
                    repo = repos.get(s.get("repository_id"), {})
                    need(bool(repo.get("remote_head")) and repo.get("remote_head") == repo.get("head") and
                         repo.get("remote_ref") == "refs/heads/" + repo.get("branch", "") and
                         bool(repo.get("remote_receipt")) and is_digest(repo.get("remote_receipt_sha256")) and
                         repo.get("dirty") is False, "current_code requires matching remote branch receipt and clean snapshot")
        if c["status"] == "operating":
            need(any(support.get("kind") == "runtime" and s.get("provenance") == "direct" and s.get("kind") == "runtime" and
                     all(s.get(k) for k in ("environment", "deployment_revision", "trace_locator"))
                     for support, s in supports), "operating requires direct environment/version/trace evidence")
    return errors


def coverage(run, evidence):
    claims = {c["id"]: c for c in evidence["claims"]}
    sources = {s["id"]: s for s in evidence["sources"]}
    rows = []
    for q in run.get("questions", []):
        kinds = set()
        supported_claims = set()
        for cid in q.get("claim_ids", []):
            claim = claims.get(cid, {})
            if not claim.get("current") and q.get("time_scope", "current") != "historical":
                continue
            for support in claim.get("support", []):
                source = sources.get(support["source_id"], {})
                kind = source.get("kind")
                if source.get("access") != "readable" or (kind == "runtime" and claim.get("status") != "operating"):
                    continue
                kinds.add(kind)
                supported_claims.add(cid)
        missing = sorted(set(q.get("requires", [])) - kinds)
        rows.append({"id": q["id"], "status": q["status"], "missing_tiers": missing,
                     "supported_claim_ids": sorted(supported_claims), "gaps": q.get("gaps", []),
                     "complete": q["status"] == "answered" and bool(supported_claims) and not missing})
    return {"complete": bool(rows) and all(q["complete"] for q in rows), "questions": rows}


def check_files(root, run, evidence):
    errors, diagrams = [], []

    def verify(entry, label):
        try:
            path = local_path(root, entry["path"])
            if not path.is_file():
                raise ValueError("missing file")
            if not is_digest(entry.get("sha256")):
                raise ValueError("SHA-256 not recorded")
            if digest(path) != entry.get("sha256"):
                raise ValueError("hash mismatch")
            return path
        except (KeyError, ValueError, OSError, TypeError) as exc:
            errors.append(f"{label}: {exc}")
            return None

    for c in run["calls"]:
        if c.get("outcome") != "pending":
            for stream in ("stdout", "stderr"):
                if stream in c:
                    path = verify(c[stream], f"call {c.get('id')} {stream}")
                    if stream == "stdout" and path and run.get("schema_version") == 2:
                        try:
                            response = json.loads(path.read_bytes())
                        except (ValueError, UnicodeError):
                            response = {}
                        success = (c.get("exit_code") == 0 and isinstance(response, dict) and
                                   response.get("ok") is True and response.get("identity") == "user")
                        if (c.get("outcome") == "success") != success:
                            errors.append(f"call {c.get('id')}: outcome disagrees with raw response/exit code")
        if c.get("result_path"):
            try:
                if not local_path(root, c["result_path"]).is_file():
                    errors.append("legacy call result_path missing")
            except ValueError as exc:
                errors.append(str(exc))
    for s in evidence["sources"]:
        if s.get("cache"):
            verify({"path": s["cache"], "sha256": s.get("sha256")}, f"source {s['id']}")
        if s.get("kind") == "code" and run.get("schema_version") == 2:
            try:
                repo = next(r for r in run["repositories"] if r["id"] == s["repository_id"])
                path = local_path(Path(repo["path"]), s["file"])
                if digest(path) != s.get("sha256"):
                    raise ValueError("code changed since recorded read")
                if not 1 <= s["line"] <= len(path.read_text().splitlines()):
                    raise ValueError("code line out of range")
            except (ValueError, OSError, KeyError, TypeError, StopIteration) as exc:
                errors.append(f"code source {s['id']}: {exc}")
    for repo in run.get("repositories", []):
        if repo.get("remote_receipt"):
            try:
                receipt = Path(repo["remote_receipt"])
                if digest(receipt) != repo.get("remote_receipt_sha256"):
                    raise ValueError("remote receipt hash mismatch")
                fields = receipt.read_text().strip().split()
                if fields != [repo.get("remote_head"), repo.get("remote_ref")]:
                    raise ValueError("remote receipt does not match recorded branch/head")
            except (ValueError, OSError) as exc:
                errors.append(f"repository {repo.get('id')}: {exc}")
    for name, artifact in run.get("artifacts", {}).items():
        # Version 1 historically used absolute artifact paths.
        if run.get("schema_version") == 1 and Path(artifact.get("path", "")).is_absolute():
            artifact = dict(artifact)
            try:
                artifact["path"] = str(Path(artifact["path"]).relative_to(root.resolve()))
            except ValueError:
                errors.append(f"artifact {name}: outside task directory")
                continue
        path = verify(artifact, f"artifact {name}")
        if not path:
            continue
        if path.suffix == ".md":
            text = path.read_text()
            for raw in re.findall(r"\]\((<[^>]+>|[^)]+)\)", text):
                target = unquote(raw.strip("<>"))
                if re.match(r"[A-Za-z][A-Za-z0-9+.-]*://|#", target):
                    continue
                target = target.split("#", 1)[0]
                match = re.fullmatch(r"(.+):(\d+)", target)
                target_path = Path(match[1] if match else target)
                if not target_path.is_absolute():
                    target_path = path.parent / target_path
                if not target_path.exists():
                    errors.append(f"broken local link: {raw}")
                elif match and (not target_path.is_file() or not 1 <= int(match[2]) <= len(target_path.read_text().splitlines())):
                    errors.append(f"invalid code line: {raw}")
            for block in re.findall(r"```mermaid\s*\n(.*?)```", text, re.S):
                matched = False
                for candidate in run.get("artifacts", {}).values():
                    try:
                        cp = local_path(root, candidate.get("path", ""))
                        receipt = candidate.get("mermaid", {})
                        if cp.suffix == ".mmd" and cp.is_file() and cp.read_text().strip() == block.strip() and receipt.get("status") == "passed" and receipt.get("parser") and receipt.get("sha256") == digest(cp):
                            matched = True
                    except (ValueError, OSError):
                        pass
                diagrams.append({"artifact": name, "status": "passed" if matched else "not_checked"})
        if path.suffix == ".mmd":
            syntax = artifact.get("mermaid", {})
            status = syntax.get("status", "not_checked")
            if status == "passed" and (syntax.get("sha256") != digest(path) or not syntax.get("parser")):
                errors.append(f"{name}: stale/missing Mermaid parser receipt")
                status = "stale"
            if status == "failed":
                errors.append(f"{name}: Mermaid syntax failed")
            diagrams.append({"artifact": name, "status": status})
    return errors, diagrams


def assess(root, run, evidence, validator):
    from check_artifacts import active_seconds, budget_status
    record_errors = validator(run, evidence)
    file_errors, diagrams = check_files(root, run, evidence)
    seconds = active_seconds(run)
    budget = {p: budget_status(run, p) for p in ("collection", "delivery")}
    matrix = coverage(run, evidence)
    pending = [c.get("id") for c in run["calls"] if c.get("outcome") == "pending"]
    warnings = []
    if run.get("schema_version") == 1:
        warnings.append("Legacy v1: fetch times, execution context and question coverage cannot be reconstructed; no automatic upgrade.")
    if any(x["status"] != "passed" for x in diagrams):
        warnings.append("Mermaid is not fully syntax-verified; no visual verification implied.")
    if any(v != "available" for v in budget.values()):
        warnings.append("Budget exhausted: stop new retrieval; validation success does not grant continuation.")
    unresolved = [k for k, v in run["operations"].items() if v and v[-1]["status"] in ("inflight", "unknown", "submitted")]
    suffixes = {Path(a.get("path", "")).suffix for a in run.get("artifacts", {}).values()}
    missing = []
    if ".md" not in suffixes:
        missing.append("local Markdown report")
    if run["delivery"]["html"] and ".html" not in suffixes:
        missing.append("requested local HTML")
    for kind in ("document", "publish"):
        attempts = run["operations"][kind]
        if run["delivery"][kind] and (not attempts or attempts[-1]["status"] != "succeeded"):
            missing.append("requested " + kind + " receipt")
    counts = {p: sum(c["phase"] == p for c in run["calls"]) for p in ("collection", "delivery")}
    counts["total"] = len(run["calls"])
    totals = {**seconds, "total": sum(seconds.values())}
    overrun = [p for p in counts if counts[p] > run["limits"][p]["calls"] or totals[p] > run["limits"][p]["seconds"]]
    return {"record_valid": not record_errors, "artifacts_valid": not file_errors,
            "budget_status": budget, "active_seconds": seconds, "question_coverage": matrix,
            "budget_compliant": not overrun, "budget_overrun_phases": overrun,
            "call_counts": {"reserved": len(run["calls"]), "sealed": len(run["calls"]) - len(pending), "pending": len(pending)},
            "delivery_complete": not (missing or record_errors or file_errors or pending or unresolved) and matrix["complete"] and all(d["status"] == "passed" for d in diagrams),
            "delivery_missing": missing,
            "record_errors": record_errors, "artifact_errors": file_errors, "diagrams": diagrams,
            "pending_calls": pending, "unresolved_operations": unresolved, "warnings": warnings,
            "fact_accuracy": "not_automatically_verified"}
