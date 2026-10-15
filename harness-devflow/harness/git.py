"""Git operations use argument vectors and the explicit consumer checkout."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess

from .model import HarnessError, require


EXCLUDES = (":(exclude).harness/runs/**", ":(exclude).harness/worktrees/**")


def content_fingerprint(root: Path) -> str:
    """Actual working bytes, names and executable bits, independent of index/HEAD.

    Submodules are deliberately unsupported for reusable evidence: their checked-out
    dependencies need a separate recursive contract. Delivery still uses fingerprint().
    """
    import os
    tracked = git(root, "ls-files", "--stage", "-z", "--", ".", *EXCLUDES)
    require(not any(entry.startswith("160000 ") for entry in tracked.split("\0")),
            "Check reuse does not support submodules")
    names = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", ".", *EXCLUDES, strip=False)
    value = hashlib.sha256()
    for name in sorted(set(names.split("\0")) - {""}):
        path = root / name
        if not path.exists() and not path.is_symlink():
            continue  # A deleted tracked file and its committed deletion have identical inputs.
        value.update(name.encode("utf-8", errors="surrogateescape") + b"\0")
        if path.is_symlink():
            value.update(b"link\0" + os.fsencode(os.readlink(path)) + b"\0")
        else:
            require(path.is_file(), f"Unsupported check input: {name}")
            value.update(b"exec\0" if path.stat().st_mode & 0o111 else b"file\0")
            value.update(hashlib.sha256(path.read_bytes()).digest())
    return value.hexdigest()


def git(root: Path, *args: str, check: bool = True, strip: bool = True) -> str:
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                                encoding="utf-8", errors="surrogateescape", timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HarnessError(f"Git failed: {error}") from error
    if check and result.returncode:
        raise HarnessError(f"git {' '.join(args[:3])}: {result.stderr.strip()}")
    return result.stdout.strip() if check and strip else result.stdout


def repo_root(path: Path) -> Path:
    return Path(git(path.resolve(), "rev-parse", "--show-toplevel")).resolve()


def branch(root: Path) -> str | None:
    value = git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).strip()
    return value or None


def common_dir(root: Path) -> str:
    return str((root / git(root, "rev-parse", "--git-common-dir")).resolve())


def head(root: Path) -> str:
    return git(root, "rev-parse", "--verify", "HEAD")


def clean(root: Path) -> bool:
    return not git(root, "status", "--porcelain", "--untracked-files=all", "--", ".", *EXCLUDES)


def fingerprint(root: Path) -> str:
    """Include HEAD, unstaged/staged bytes, untracked bytes, names and modes."""
    value = hashlib.sha256(head(root).encode())
    diff = git(root, "diff", "--no-ext-diff", "--binary", "HEAD", "--", ".", *EXCLUDES)
    value.update(diff.encode("utf-8", errors="surrogateescape"))
    files = git(root, "ls-files", "--others", "--exclude-standard", "-z", "--", ".", *EXCLUDES)
    for name in sorted(files.split("\0")):
        if not name:
            continue
        path = root / name
        value.update(name.encode("utf-8", errors="surrogateescape") + b"\0")
        if path.is_symlink():
            import os
            value.update(os.readlink(path).encode("utf-8", errors="surrogateescape"))
        elif path.is_file():
            value.update(str(path.stat().st_mode).encode())
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    value.update(chunk)
    return value.hexdigest()


def is_ancestor(root: Path, older: str, newer: str = "HEAD") -> bool:
    result = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", older, newer],
                            capture_output=True, timeout=60)
    require(result.returncode in (0, 1), "Could not verify Git ancestry")
    return result.returncode == 0
