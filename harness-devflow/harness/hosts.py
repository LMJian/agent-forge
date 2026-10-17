"""Host capability selection. Availability is explicit, never inferred from a brand."""
from __future__ import annotations

from pathlib import Path

from . import git as vcs
from .model import identifier, require, strings, validate_command


CAPABILITIES = {"worktree", "delegation", "scheduling"}


def defaults() -> dict:
    return {"name": "codex", "available": [], "command": {"provider": "auto"},
            "worktree": "auto"}


def validate(value: object) -> dict:
    require(isinstance(value, dict) and set(value) <= set(defaults()), "Unknown host option")
    config = {**defaults(), **value}
    identifier(config["name"])
    available = strings(config["available"], "host.available", empty=True)
    require(set(available) <= CAPABILITIES, "Unknown host capability")
    command = config["command"]
    require(isinstance(command, dict) and set(command) <= {"provider", "bridge"}, "Invalid host.command")
    command = {"provider": "auto", **command}
    require(command["provider"] in {"auto", "builtin", "native"}, "Invalid command provider")
    if "bridge" in command:
        validate_command(command["bridge"], "host.command.bridge")
    require(command["provider"] != "native" or "bridge" in command,
            "Native commands need an explicitly configured host.command.bridge")
    require(config["worktree"] in {"auto", "builtin", "native"}, "Invalid worktree provider")
    require(config["worktree"] != "native" or "worktree" in available,
            "Native worktree capability is unavailable")
    config["command"] = command
    return config


def resolve(config: dict, assistance: str) -> dict:
    host = validate(config)
    command = host["command"]["provider"]
    if command == "auto":
        command = "native" if "bridge" in host["command"] else "builtin"
    worktree = host["worktree"]
    if worktree == "auto":
        worktree = "native" if "worktree" in host["available"] else "builtin"
    return {"host": host["name"], "command": command, "worktree": worktree,
            "delegation": "native" if assistance == "autonomous" and "delegation" in host["available"] else "serial",
            "monitoring": "native" if "scheduling" in host["available"] else "on_demand"}


def module_path(workflow, item: dict) -> Path:
    """Native worktrees may be outside the checkout, but must belong to the same Git repo."""
    from .storage import inside
    path = Path(item["worktree"]).resolve()
    if item.get("provider") == "native":
        require(path != workflow.root and vcs.repo_root(path) == path and
                vcs.common_dir(path) == vcs.common_dir(workflow.root), "Native worktree repository mismatch")
    else:
        path = inside(workflow.root, path)
    require(vcs.branch(path) == item["branch"], "Module worktree branch changed")
    return path
