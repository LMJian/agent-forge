#!/usr/bin/env python3
"""Collect a bounded, read-only evidence inventory for brownfield investigation."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Any, Iterable


SCHEMA_VERSION = "brownfield-recon-evidence-v1"
SKIP_DIRS = {
    ".git",
    ".artifacts",
    ".harness",
    ".cache",
    ".idea",
    ".vscode",
    "build",
    "dist",
    "node_modules",
    "output",
    "target",
    "tmp",
    "vendor",
    "__pycache__",
}
SENSITIVE_PART_RE = re.compile(
    r"(^|/)(\.env(?:\.[^/]*)?|[^/]*\.env(?:\.[^/]*)?|[^/]*credential[^/]*|[^/]*private[_-]?key[^/]*|id_(?:rsa|dsa|ecdsa|ed25519)(?:\.[^/]*)?|[^/]*token[_-]?dump[^/]*|tokens?\.(?:json|txt)|[^/]*\.(?:pem|key|p12|pfx)|\.(?:netrc|npmrc|pypirc)|\.ssh|\.aws|secrets?(?:[._-][^/]*)?\.(?:json|ya?ml|toml|ini|txt)|service[-_]account(?:[._-][^/]*)?\.json)($|/)",
    re.IGNORECASE,
)
GENERATED_RE = re.compile(r"(^|/)(gen|generated|kitex_gen|thrift_gen)(/|$)|\.pb\.go$", re.IGNORECASE)
CONTRACT_SUFFIXES = {".thrift", ".proto", ".avdl", ".graphql", ".gql"}
CONFIG_SUFFIXES = {".yaml", ".yml", ".toml", ".ini"}
TEST_RE = re.compile(r"(^|/)(test|tests|testing)(/|$)|(_test\.|\.test\.)", re.IGNORECASE)
DEFAULT_SEARCH_BYTES = 256 * 1024
DEFAULT_SEARCH_SECONDS = 15.0
VALUE_RE = re.compile(
    r'''(?i)(\b(?:password|passwd|api[_-]?key|(?:access|client|app)[_-]?secret|secret(?:[_-]?key)?|private[_-]?key|(?:access|refresh|id)[_-]?token|token|_auth(?:Token)?|_password)\b["']?\s*[:=]\s*)("(?:\\.|[^"\\\r\n])*"|'(?:\\.|[^'\\\r\n])*'|[^\r\n]+)'''
)
AUTH_RE = re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9+/_.=:-]+")
URL_AUTH_RE = re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@")


def redact(text: str) -> str:
    text = AUTH_RE.sub(r"\1 [REDACTED]", text)
    text = URL_AUTH_RE.sub(r"\1[REDACTED]@", text)
    return VALUE_RE.sub(lambda match: match[1] + "[REDACTED]", text)


def run(cmd: list[str], cwd: Path, timeout: float = 30,
        max_output_bytes: int = 1024 * 1024) -> tuple[int, str, str]:
    """Drain both pipes with byte/deadline limits, before materializing output.

    124/125/127 distinguish timeout, output-budget exhaustion and launch failure.
    Callers must not treat their partial stdout as a complete negative result.
    """
    output, errors = bytearray(), bytearray()
    events: queue.Queue = queue.Queue(maxsize=4)
    stop = threading.Event()
    readers = []
    proc = None
    code, reason = None, ""

    def drain(stream, target, limit):
        # Bounded queues also work for Windows anonymous pipes, unlike selectors.
        # The reader owns closing its pipe; a lingering descendant cannot make
        # the main thread block indefinitely while closing a locked read buffer.
        with stream:
            while not stop.is_set():
                chunk = stream.read1(min(4096, limit + 1))
                while not stop.is_set():
                    try:
                        events.put((target, limit, chunk), timeout=0.05)
                        break
                    except queue.Full:
                        continue
                if not chunk:
                    break

    try:
        proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=(os.name == "posix"))
        deadline = time.monotonic() + timeout
        for stream, target, limit in [(proc.stdout, output, max_output_bytes), (proc.stderr, errors, 16 * 1024)]:
            reader = threading.Thread(target=drain, args=(stream, target, limit), daemon=True)
            reader.start()
            readers.append(reader)
        open_pipes = 2
        while open_pipes:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                code, reason = 124, "command timeout"
                break
            try:
                target, limit, chunk = events.get(timeout=min(remaining, 0.1))
            except queue.Empty:
                continue
            if not chunk:
                open_pipes -= 1
            elif len(target) + len(chunk) > limit:
                target.extend(chunk[:limit - len(target)])
                code, reason = 125, "command output byte budget exhausted"
                break
            else:
                target.extend(chunk)
        if code is None:
            try:
                code = proc.wait(timeout=max(0.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                code, reason = 124, "command timeout"
        return code, output.decode("utf-8", errors="replace"), redact(errors.decode("utf-8", errors="replace") + reason)
    except OSError as exc:
        return 127, "", redact(str(exc))
    finally:
        stop.set()
        if proc is not None:
            if os.name == "posix" and (proc.poll() is None or code in (124, 125)):
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif proc.poll() is None:
                proc.kill()
            proc.wait()
            for reader in readers:
                reader.join(timeout=0.2)


def is_sensitive(rel: str) -> bool:
    return bool(SENSITIVE_PART_RE.search(rel.replace(os.sep, "/")))


def source_file_allowed(root: Path, rel: str) -> bool:
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts or is_sensitive(rel):
        return False
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    # The same check runs before inventory and before passing paths to rg.
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            return False
    return current.is_file()


def normalize_scopes(root: Path, scopes: list[str]) -> list[str]:
    result = []
    for scope in scopes:
        path = Path(scope)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("scope must be a repository-relative path without '..'")
        current = root
        for part in path.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("scope cannot traverse a symlink")
        if not current.exists() or is_sensitive(scope) or any(part in SKIP_DIRS for part in path.parts):
            raise ValueError("scope must name an existing, non-sensitive source path")
        result.append(path.as_posix())
    return sorted(set(result))


def fallback_files(root: Path, scopes: list[str] | None = None) -> list[str]:
    files: set[str] = set()
    for scope in scopes or ["."]:
        start = root / scope
        if start.is_file():
            if source_file_allowed(root, scope):
                files.add(Path(scope).as_posix())
            continue
        for current, dirs, names in os.walk(start):
            current_path = Path(current)
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS
                       and not is_sensitive((current_path / d).relative_to(root).as_posix())
                       and not (current_path / d).is_symlink()]
            for name in names:
                rel = (current_path / name).relative_to(root).as_posix()
                if source_file_allowed(root, rel):
                    files.add(rel)
    return sorted(files)


def list_files(root: Path, warnings: list[str], scopes: list[str] | None = None) -> list[str]:
    if shutil.which("rg"):
        cmd = ["rg", "--files", "-0", "--hidden", "--no-ignore-vcs", "--no-config"]
        for directory in sorted(SKIP_DIRS):
            cmd.extend(["-g", f"!{directory}/**", "-g", f"!**/{directory}/**"])
        cmd.extend(["--", *(scopes or ["."])])
        rc, out, err = run(cmd, root)
        if rc in (0, 1):
            files = [Path(p).as_posix() for p in out.split("\0") if p]
            return sorted(set(p for p in files if source_file_allowed(root, p)))
        warnings.append(f"rg --files failed: {err.strip() or f'rc={rc}'}")
    else:
        warnings.append("rg unavailable; used os.walk fallback")
    return fallback_files(root, scopes)


def bounded(items: Iterable[str], limit: int) -> list[str]:
    return list(items)[:limit]


def classify(files: list[str], limit: int) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {
        "contracts": [],
        "configuration": [],
        "persistence": [],
        "generated": [],
        "tests": [],
        "documentation": [],
        "entrypoints": [],
        "outbound_clients": [],
    }
    for rel in files:
        low = rel.lower()
        path = Path(rel)
        suffix = path.suffix.lower()
        parts = set(path.parts)
        if suffix in CONTRACT_SUFFIXES or "idl" in parts or "schema" in parts:
            result["contracts"].append(rel)
        if suffix in CONFIG_SUFFIXES or any(k in low for k in ("config", "/conf/", "tcc", "feature_gate", "/fg")):
            result["configuration"].append(rel)
        if any(k in low for k in ("persistence", "migration", "repository", "/repo/", "leveldb", "redis", "mysql", ".sql")):
            result["persistence"].append(rel)
        if GENERATED_RE.search(rel):
            result["generated"].append(rel)
        if TEST_RE.search(rel):
            result["tests"].append(rel)
        if suffix in {".md", ".rst", ".adoc"} or parts.intersection({"docs", "requirements", "design"}):
            result["documentation"].append(rel)
        # Fix #4: 'client' is an outbound/downstream signal, not an inbound entrypoint.
        # Keep it in a dedicated bucket so the entrypoint map stays low-noise.
        if "client" in low:
            result["outbound_clients"].append(rel)
        # Inbound entrypoints: process mains, or inbound handlers whose path also
        # carries an inbound signal (api/rpc/http/cmd/server dir) to reduce noise.
        inbound_dir = any(k in low for k in ("/api/", "/rpc/", "/http/", "/cmd/", "/server/", "/entry"))
        inbound_role = any(k in low for k in ("handler", "controller", "router"))
        if path.name in {"main.go", "main.py", "main.rs", "index.ts", "index.js"} or (
            inbound_role and inbound_dir
        ) or (inbound_role and not any(k in low for k in ("client", "downstream", "outbound"))):
            result["entrypoints"].append(rel)
    return {name: bounded(sorted(set(paths)), limit) for name, paths in result.items()}


def parse_commits(text: str) -> list[dict[str, str]]:
    commits: list[dict[str, str]] = []
    for line in text.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 4:
            commits.append({"hash": parts[0], "date": parts[1], "author": parts[2], "subject": parts[3]})
    return commits


def git_ref_exists(root: Path, ref: str) -> bool:
    rc, _, _ = run(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], root)
    return rc == 0


def detect_base_ref(root: Path, requested: str | None, warnings: list[str]) -> str | None:
    if requested:
        if git_ref_exists(root, requested):
            return requested
        # Fix #2: never silently downgrade an explicit --base-ref; surface it.
        fallback = None
        for ref in ("origin/master", "origin/main", "master", "main"):
            if git_ref_exists(root, ref):
                fallback = ref
                break
        warnings.append(
            f"requested base-ref {requested!r} not found; "
            + (
                f"falling back to {fallback!r}"
                if fallback
                else "no fallback base available, using recent-commit window"
            )
        )
        return fallback
    for ref in ("origin/master", "origin/main", "master", "main"):
        if git_ref_exists(root, ref):
            return ref
    return None


def parse_numstat(text: str, limit: int) -> list[dict[str, Any]]:
    stats: dict[str, dict[str, int]] = collections.defaultdict(lambda: {"added": 0, "deleted": 0, "touches": 0})
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        added, deleted, path = int(parts[0]), int(parts[1]), parts[2]
        stats[path]["added"] += added
        stats[path]["deleted"] += deleted
        stats[path]["touches"] += 1
    rows = [
        {
            "path": path,
            **values,
            "churn": values["added"] + values["deleted"],
            "generated": bool(GENERATED_RE.search(path)),
        }
        for path, values in stats.items()
    ]
    rows.sort(key=lambda row: (row["churn"], row["touches"], row["path"]), reverse=True)
    return rows[:limit]


def git_evidence(root: Path, base_ref: str | None, max_commits: int, limit: int, warnings: list[str]) -> dict[str, Any]:
    rc, top, _ = run(["git", "rev-parse", "--show-toplevel"], root)
    if rc != 0:
        warnings.append("not a Git worktree; Git history unavailable")
        return {"available": False}

    failures = []

    def query(label: str, args: list[str], timeout: float = 30) -> str:
        code, text, error = run(["git", *args], root, timeout=timeout)
        if code:
            failures.append({"operation": label, "returncode": code})
            warnings.append(f"git {label} incomplete: {error.strip() or f'rc={code}'}")
        return text if code == 0 else ""

    branch = query("branch", ["branch", "--show-current"])
    head = query("head", ["rev-parse", "HEAD"])
    status = query("status", ["status", "--short"])
    log_text = query("recent history", ["log", f"-{max_commits}", "--date=iso-strict", "--format=%H%x1f%ad%x1f%an%x1f%s"])

    base = detect_base_ref(root, base_ref, warnings)
    diff_files: list[dict[str, str]] = []
    diff_stat = ""
    # git log A...B is symmetric history; git diff A...B is not. Resolve the
    # merge base, then use only its descendants on HEAD for branch evidence.
    churn_range = f"-{max_commits}"
    diff_semantics = "recent-commit-window"
    merge_base = ""
    if base:
        merge_base = query("merge base", ["merge-base", base, "HEAD"]).strip()
        if merge_base:
            branch_range = f"{merge_base}..HEAD"
            names = query("diff names", ["diff", "--name-status", branch_range])
            for line in names.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2:
                    diff_files.append({"status": parts[0], "path": parts[-1]})
            diff_stat = query("diff stat", ["diff", "--stat", branch_range])
            churn_range = branch_range
            diff_semantics = "merge-base to HEAD (two-dot range after resolution)"
        else:
            diff_semantics = "unavailable: merge base could not be resolved"

    numstat = query("hotspots", ["log", "--numstat", "--format=", churn_range], timeout=60) if not base or merge_base else ""
    base_commit = query("base commit", ["rev-parse", "--verify", f"{base}^{{commit}}"] ) if base else ""
    working = query("working-tree diff", ["diff", "HEAD", "--name-status"])
    working_files = []
    for line in working.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            working_files.append({"status": parts[0], "path": parts[-1]})
    return {
        "available": True,
        "root": top.strip(),
        "branch": branch.strip(),
        "head": head.strip(),
        "base_ref": base,
        "base_commit": base_commit.strip() or None,
        "base_resolution": "fallback" if base_ref and base_ref != base else "exact" if base_ref else "auto",
        "merge_base_commit": merge_base or None,
        "complete": not failures,
        "command_errors": failures,
        "working_tree_diff_semantics": "tracked index and worktree vs HEAD; see dirty_paths for untracked files",
        "working_tree_diff_files": working_files[:limit],
        "working_tree_diff_truncated": max(0, len(working_files) - limit),
        "diff_semantics": diff_semantics,
        "churn_range": churn_range,
        "dirty_paths": [line[3:] if len(line) > 3 else line for line in status.splitlines()],
        "recent_commits": parse_commits(log_text),
        "branch_diff_files": diff_files[:limit],
        "branch_diff_truncated": max(0, len(diff_files) - limit),
        "branch_diff_stat": diff_stat.strip(),
        "history_hotspots": parse_numstat(numstat, limit),
    }


def keyword_hits(
    root: Path,
    keywords: list[str],
    max_hits: int,
    warnings: list[str],
    fixed: bool = True,
    files: list[str] | None = None,
    searches: dict[str, Any] | None = None,
    byte_budget: int = DEFAULT_SEARCH_BYTES,
    search_timeout: float = DEFAULT_SEARCH_SECONDS,
) -> dict[str, list[dict[str, Any]]]:
    """Keep legacy hits while exposing coverage/outcomes in a separate mapping."""
    results: dict[str, list[dict[str, Any]]] = {}
    searches = searches if searches is not None else {}
    if not keywords:
        return results
    if not shutil.which("rg"):
        warnings.append("rg unavailable; keyword content search skipped")
        for keyword in keywords:
            results[keyword] = []
            searches[keyword] = {"status": "unavailable", "complete": False,
                                 "error_kind": "missing_tool", "completed_files": 0,
                                 "returned_matches": 0, "reason_codes": ["missing_rg"]}
        return results
    selected = list_files(root, warnings) if files is None else files
    # Never scan the repository root and filter secrets after reading them. Pass
    # only the approved regular files, in bounded batches, to the search process.
    safe_files = []
    skipped = {"filtered_or_missing": 0, "oversized": 0}
    for path in selected:
        if not source_file_allowed(root, path):
            skipped["filtered_or_missing"] += 1
            continue
        try:
            # rg may ignore --max-filesize for explicit file arguments.
            if (root / path).stat().st_size > 2 << 20:
                skipped["oversized"] += 1
                continue
        except OSError:
            warnings.append(f"source disappeared before search: {path}")
            skipped["filtered_or_missing"] += 1
            continue
        safe_files.append(path)
    if skipped["oversized"]:
        warnings.append(f"{skipped['oversized']} source files exceed 2 MiB; content search skipped them")
    for keyword in keywords:
        hits: list[dict[str, Any]] = []
        started = time.monotonic()
        reasons = [f"skipped_{key}" for key, count in skipped.items() if count]
        output_bytes, completed_files, attempted_files = 0, 0, 0
        error_kind, error_text = None, None
        for offset in range(0, len(safe_files), 32):
            remaining_time = search_timeout - (time.monotonic() - started)
            if remaining_time <= 0:
                error_kind = "timeout"
                reasons.append("time_budget")
                break
            if output_bytes >= byte_budget:
                reasons.append("byte_budget")
                break
            batch = safe_files[offset:offset + 32]
            cmd = ["rg", "--json", "--no-config", "--max-filesize", "2M",
                   "--max-count", str(max_hits + 1)]
            if fixed:
                cmd.append("-F")
            cmd.extend(["--", keyword, *batch])
            attempted_files += len(batch)
            rc, out, err = run(cmd, root, timeout=remaining_time,
                               max_output_bytes=byte_budget - output_bytes)
            output_bytes += min(len(out.encode("utf-8")), byte_budget - output_bytes)
            ended = set()
            for line in out.splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    if rc not in (124, 125):
                        error_kind, error_text = "invalid_output", "rg returned malformed JSON"
                    break  # A budget may cut the final JSON event in the middle.
                if not isinstance(event, dict):
                    error_kind, error_text = "invalid_output", "rg returned a non-object event"
                    break
                kind, data = event.get("type"), event.get("data")
                if not isinstance(kind, str) or kind not in {"begin", "match", "context", "end", "summary"}:
                    error_kind, error_text = "invalid_output", "rg returned an unknown event type"
                    break
                if kind in {"match", "end"} and (not isinstance(data, dict) or not isinstance(data.get("path"), dict)):
                    error_kind, error_text = "invalid_output", "rg event has no valid path"
                    break
                if kind == "end":
                    if data["path"].get("text") is not None and not isinstance(data["path"]["text"], str):
                        error_kind, error_text = "invalid_output", "rg returned an invalid path value"
                        break
                    ended.add(data["path"].get("text"))
                if kind != "match":
                    continue
                if not isinstance(data.get("lines"), dict) or not isinstance(data.get("line_number"), int):
                    error_kind, error_text = "invalid_output", "rg match has no valid line"
                    break
                path, text = data["path"].get("text"), data["lines"].get("text")
                if path is None or text is None:
                    reasons.append("non_text_event")
                    continue
                if not isinstance(path, str) or not isinstance(text, str):
                    error_kind, error_text = "invalid_output", "rg returned an invalid match value"
                    break
                if len(hits) >= max_hits:
                    reasons.append("hit_limit")
                    break
                hits.append({"path": path, "line": data["line_number"], "text": redact(text.rstrip("\r\n"))[:500]})
            completed_files += len(batch) if rc in (0, 1) and error_kind is None else len(ended - {None})
            if rc == 125:
                reasons.append("byte_budget")
            elif rc == 124:
                error_kind, error_text = "timeout", "query exceeded its time budget"
                reasons.append("time_budget")
            elif rc not in (0, 1):
                error_kind = "missing_tool" if rc == 127 else "command_error"
                error_text = redact(err.strip())[:300] or f"rc={rc}"
            if error_kind or rc not in (0, 1):
                break
            if len(hits) >= max_hits:
                if offset + len(batch) < len(safe_files):
                    reasons.append("hit_limit")
                break
        reasons = sorted(set(reasons))
        complete = not reasons and error_kind is None
        status = ("unavailable" if error_kind == "missing_tool" else "error" if error_kind else
                  "partial" if not complete else "matched" if hits else "no_match")
        searches[keyword] = {"status": status, "complete": complete,
                             "error_kind": error_kind, "error": error_text,
                             "candidate_files": len(selected), "eligible_files": len(safe_files),
                             "attempted_files": attempted_files, "completed_files": completed_files,
                             "skipped_files": dict(skipped), "returned_matches": len(hits),
                             "reason_codes": reasons, "output_bytes": output_bytes,
                             "byte_budget": byte_budget, "time_budget_seconds": search_timeout,
                             "elapsed_seconds": round(time.monotonic() - started, 3)}
        if not complete:
            warnings.append(f"keyword {redact(keyword)!r} {status}: {error_text or ', '.join(reasons)}; not proof of absence")
        results[keyword] = hits
    return results


def knowledge_evidence(root: Path, limit: int, selected: list[str] | None = None) -> dict[str, Any]:
    paths = selected or [str(root / name) for name in (".ai_knowledge", ".artifacts")
                         if (root / name).is_dir()]
    sources = []
    combined: list[str] = []
    for value in paths:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = root / path
        # Knowledge collection is metadata-only; content is read selectively by
        # the agent through the source's normal access mechanism.
        if is_sensitive(path.as_posix()) or any(p.is_symlink() for p in [path, *path.parents]):
            sources.append({"path": str(path), "present": False, "skipped": "sensitive or symlink path"})
            continue
        present = path.is_dir() or path.is_file()
        names: list[str] = []
        truncated = False
        if path.is_file():
            names.append(str(path))
        elif path.is_dir():
            for current, dirs, files in os.walk(path):
                base = Path(current)
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS
                                 and not is_sensitive(d) and not (base / d).is_symlink())
                for name in sorted(files):
                    file = base / name
                    if is_sensitive(name) or file.is_symlink() or not file.is_file():
                        continue
                    if len(names) >= limit:
                        truncated = True
                        break
                    names.append(str(file))
                if truncated:
                    break
        combined.extend(names)
        sources.append({"path": str(path), "present": present, "files": names,
                        "truncated": truncated, "has_index": (path / "index.md").is_file() if path.is_dir() else False})
    return {"present": any(s["present"] for s in sources), "roots": sources,
            "files": combined[:limit], "truncated": len(combined) > limit or any(s.get("truncated", False) for s in sources)}


def devflow_evidence(root: Path, limit: int, warnings: list[str]) -> list[dict[str, Any]]:
    artifacts = root / ".artifacts"
    if not artifacts.is_dir():
        return []
    states: list[dict[str, Any]] = []
    for path in sorted(artifacts.glob("*/state.json"))[:limit]:
        try:
            if any(node.is_symlink() for node in [path, *path.parents] if node.is_relative_to(root)):
                warnings.append(f"skipped symlink workflow state: {path.relative_to(root)}")
                continue
            if path.stat().st_size > 2 << 20:
                raise ValueError("workflow state exceeds 2 MiB")
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("workflow state must be an object")
            stages = data.get("stages") or {}
            if not isinstance(stages, dict):
                raise ValueError("workflow stages must be an object")
            states.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "feature": data.get("feature"),
                    "branch": data.get("branch"),
                    "current_stage": data.get("current_stage"),
                    "revision": data.get("revision"),
                    "stage_statuses": {name: value.get("status") for name, value in stages.items() if isinstance(value, dict)},
                }
            )
        except (OSError, ValueError) as exc:
            warnings.append(f"cannot parse {path.relative_to(root)}: {exc}")
    return states


def inventory(files: list[str]) -> dict[str, Any]:
    suffixes = collections.Counter(Path(path).suffix.lower() or "<none>" for path in files)
    top_dirs = collections.Counter(Path(path).parts[0] if len(Path(path).parts) > 1 else "." for path in files)
    return {
        "file_count": len(files),
        "extensions": [{"extension": ext, "count": count} for ext, count in suffixes.most_common(20)],
        "top_level": [{"path": path, "count": count} for path, count in top_dirs.most_common(30)],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root to inspect")
    parser.add_argument("--base-ref", help="Base branch or commit for branch diff")
    parser.add_argument("--scope", action="append", default=[], help="Repository-relative source path; repeatable")
    parser.add_argument("--knowledge-root", action="append", default=[], help="Knowledge file/directory; relative to repo-root; repeatable")
    parser.add_argument("--keyword", action="append", default=[], help="Exact fixed-string keyword; repeatable")
    parser.add_argument(
        "--regex-keyword",
        action="append",
        default=[],
        help="Regex keyword (rg without -F); use after learning local naming; repeatable",
    )
    parser.add_argument("--max-hits", type=int, default=50, help="Maximum content hits per keyword")
    parser.add_argument("--search-byte-budget", type=int, default=DEFAULT_SEARCH_BYTES,
                        help="Maximum raw stdout bytes per keyword, across all batches")
    parser.add_argument("--search-timeout", type=float, default=DEFAULT_SEARCH_SECONDS,
                        help="Total seconds per keyword, across all batches")
    parser.add_argument("--max-commits", type=int, default=40, help="Recent commits and fallback churn window")
    parser.add_argument("--limit", type=int, default=80, help="Maximum items per bounded inventory section")
    parser.add_argument("--output", default="-", help="JSON output path, or - for stdout")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.repo_root).expanduser().resolve()
    if not root.is_dir():
        print(f"repository root does not exist: {root}", file=sys.stderr)
        return 2
    if (min(args.max_hits, args.max_commits, args.limit, args.search_byte_budget, args.search_timeout) <= 0
            or not math.isfinite(args.search_timeout)):
        print("limits and search budgets must be positive", file=sys.stderr)
        return 2

    try:
        scopes = normalize_scopes(root, args.scope)
        output = None if args.output == "-" else Path(args.output).expanduser().resolve()
        if output is not None:
            if output.is_relative_to(root):
                parts = output.relative_to(root).parts
                allowed = parts and (parts[0] == ".artifacts" or
                                     (len(parts) >= 5 and parts[:2] == (".harness", "runs") and parts[3] == "artifacts"))
                if not allowed:
                    raise ValueError("output inside the repository must be under .artifacts/ or .harness/runs/<task>/artifacts/")
            if output.exists():
                raise ValueError("evidence already exists; choose a new filename to preserve the baseline")
    except (ValueError, IndexError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    warnings: list[str] = []
    files = list_files(root, warnings, scopes)
    fixed_searches, regex_searches = {}, {}
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "repo_root": str(root),
        "parameters": {
            "base_ref": args.base_ref,
            "scopes": scopes,
            "knowledge_roots": args.knowledge_root,
            "keywords": args.keyword,
            "regex_keywords": args.regex_keyword,
            "max_hits": args.max_hits,
            "max_commits": args.max_commits,
            "limit": args.limit,
            "search_byte_budget": args.search_byte_budget,
            "search_timeout": args.search_timeout,
        },
        "inventory": inventory(files),
        "candidates": classify(files, args.limit),
        "keyword_hits": keyword_hits(root, args.keyword, args.max_hits, warnings, fixed=True, files=files,
                                     searches=fixed_searches, byte_budget=args.search_byte_budget, search_timeout=args.search_timeout),
        "regex_keyword_hits": keyword_hits(root, args.regex_keyword, args.max_hits, warnings, fixed=False, files=files,
                                           searches=regex_searches, byte_budget=args.search_byte_budget, search_timeout=args.search_timeout),
        "searches": {"fixed": fixed_searches, "regex": regex_searches},
        "git": git_evidence(root, args.base_ref, args.max_commits, args.limit, warnings),
        "knowledge": knowledge_evidence(root, args.limit, args.knowledge_root),
        "devflow": devflow_evidence(root, args.limit, warnings),
        "warnings": warnings,
        "safety": {
            "read_only_scan": True,
            "skipped_directories": sorted(SKIP_DIRS),
            "sensitive_name_filter": SENSITIVE_PART_RE.pattern,
            "content_search": "prefiltered regular files only; no symlinks; at most 2 MiB per file",
            "snippet_redaction": "credential assignments, Basic/Bearer credentials and URL userinfo; not a declassification guarantee",
        },
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output is None:
        sys.stdout.write(rendered)
    else:
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as stream:
                stream.write(rendered)
        except OSError as exc:
            print(f"cannot write evidence: {exc}", file=sys.stderr)
            return 2
        print(json.dumps({"written": str(output), "schema_version": SCHEMA_VERSION}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
