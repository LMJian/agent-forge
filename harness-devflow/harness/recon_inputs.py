"""Recon freshness follows declared source inputs, not unrelated HEAD changes.

Review and delivery retain their separate whole-checkout fingerprints.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from . import git as vcs
from .model import require
from .storage import read_json


def normalize(scopes: list[str]) -> list[str]:
    require(isinstance(scopes, list) and all(isinstance(s, str) and s for s in scopes),
            "Recon evidence_paths must be a list of repository-relative paths")
    result = []
    for scope in scopes:
        path = Path(scope)
        require(not path.is_absolute() and ".." not in path.parts,
                "Recon evidence paths cannot leave the repository")
        result.append(path.as_posix())
    return ["."] if "." in result else sorted(set(result))


def selected(path: str, scopes: list[str]) -> bool:
    return any(scope == "." or path == scope or path.startswith(scope + "/") for scope in scopes)


def snapshot(root: Path, scopes: list[str] | None = None) -> dict:
    scopes = normalize(scopes or ["."])
    paths = [f":(literal){scope}" for scope in scopes]
    tracked = vcs.git(root, "ls-files", "--stage", "-z", "--", *paths, *vcs.EXCLUDES)
    require(not any(entry.startswith("160000 ") for entry in tracked.split("\0")),
            "Recon input reuse requires a separate contract for submodules")
    names = vcs.git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--",
                    *paths, *vcs.EXCLUDES, ":(exclude).artifacts/**", strip=False)
    files = {}
    for name in sorted(set(names.split("\0")) - {""}):
        path = root / name
        require(not any(parent.is_symlink() for parent in path.parents if parent.is_relative_to(root)),
                f"Recon input cannot traverse a symlink: {name}")
        if path.is_symlink():
            files[name] = {"kind": "symlink", "sha256": hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()}
        elif path.exists():
            require(path.is_file(), f"Unsupported recon input: {name}")
            before = path.stat()
            value = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(65536), b""):
                    value.update(chunk)
            after = path.stat()
            require((before.st_ino, before.st_size, before.st_mtime_ns) ==
                    (after.st_ino, after.st_size, after.st_mtime_ns),
                    f"Code changed while capturing recon input: {name}")
            files[name] = {"kind": "file", "executable": bool(after.st_mode & 0o111), "sha256": value.hexdigest()}
    return {"schema_version": 1, "head": vcs.head(root), "files": files}


def verify(root: Path, use: dict, extra_scopes: list[str] | None = None, *, record: bool = False) -> None:
    if not use.get("recon_input_snapshot"):
        # Existing prepared invocations keep their original conservative contract.
        require(use["fingerprint"] == vcs.fingerprint(root), "Code changed during baseline investigation; reopen intake")
        return
    declared = normalize(extra_scopes if extra_scopes is not None else [])
    scopes = normalize([*normalize(use.get("recon_scopes", [])), *declared]) or ["."]
    original = read_json(Path(use["recon_input_snapshot"]))["files"]
    require(all(scope == "." or any(selected(path, [scope]) for path in original) for scope in scopes),
            "Recon evidence path has no captured source input; declare a captured parent directory")
    expected = {path: value for path, value in original.items() if selected(path, scopes)}
    require(expected == snapshot(root, scopes)["files"],
            "Code changed in the recon evidence scope; refresh the affected baseline via reopen intake")
    if record:
        use["recon_scopes"] = scopes
