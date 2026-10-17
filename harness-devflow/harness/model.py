"""Shared workflow and configuration contracts."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any


STAGES = (
    "intake", "design", "design_audit", "test_design", "design_approval",
    "interfaces", "plan", "implement", "review", "integration", "push",
    "pr", "monitor", "release", "deploy", "knowledge",
)
GATES = {"design_approval", "release", "knowledge"}
OPTIONAL = {"interfaces", "integration", "knowledge"}
CORE = {"intake", "plan", "implement", "review"}
PROFILES = ("codex", "light", "standard", "release")
ASSISTANCE = ("guided", "autonomous")
CONFIG_SCHEMA = 2
STATE_SCHEMA = 3
REPORT_SCHEMA = 2
TARGETS = ("local", "pushed", "pr", "merged", "deployed")
SELECTABLE = {"design", "design_audit", "test_design", "design_approval", "interfaces", "integration", "knowledge"}
CAPABILITY_STAGES = {"recon": "intake", "design": "design", "design_audit": "design_audit", "review": "review"}
BUNDLED_CAPABILITIES = {"brownfield-recon", "server-tech-design"}
DOMAINS = ("generic", "backend", "frontend", "mixed")
CODE_BOUND = {"review", "push", "integration", "pr", "monitor", "release", "deploy", "knowledge"}
ADAPTER_STAGES = {"interfaces", "push", "pr", "monitor", "deploy"}
TERMINAL = {"done", "skipped"}
IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


class HarnessError(Exception):
    """Expected, actionable user error (CLI exit 2)."""


def require(condition: Any, message: str) -> None:
    if not condition:
        raise HarnessError(message)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def execution_hash(config: dict) -> str:
    return digest({key: config[key] for key in ("checks", "stage_checks", "adapters", "host")})


def identifier(value: str) -> str:
    require(isinstance(value, str) and IDENTIFIER.fullmatch(value),
            "Identifiers must be 1–63 lowercase letters, digits or hyphens, starting alphanumeric")
    return value


def nonempty(value: Any, field: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{field} must be a nonempty string")
    return value


def strings(value: Any, field: str, *, empty: bool = False) -> list[str]:
    require(isinstance(value, list) and (empty or bool(value)), f"{field} must be a list")
    for item in value:
        nonempty(item, field)
    require(len(set(value)) == len(value), f"{field} contains duplicates")
    return value


def default_config() -> dict:
    from .hosts import defaults as host_defaults
    return {
        "schema_version": CONFIG_SCHEMA,
        "base_ref": None,
        "max_attempts": 3,
        "parallel_max": 4,
        "check_timeout_seconds": 300,
        "review_max_age_seconds": 7200,
        "checks": {},
        "stage_checks": {"review": [], "integration": []},
        "adapters": {},
        "workflow": workflow_defaults(),
        "host": host_defaults(),
    }


def workflow_defaults() -> dict:
    return {"profile": "codex", "target": None, "isolation": "auto", "assistance": "autonomous", "entry": "develop",
            "integration_position": "before_push", "knowledge_approval": False, "stages": {},
            "domain": "generic", "capabilities": {slot: "auto" for slot in CAPABILITY_STAGES}}


def workflow_options(value: Any) -> dict:
    require(isinstance(value, dict), "workflow must be an object")
    require(set(value) <= set(workflow_defaults()), "Unknown workflow option")
    options = {**workflow_defaults(), **value}
    require(options["profile"] in PROFILES, "Unknown workflow profile")
    require(options["assistance"] in ASSISTANCE, "Unknown assistance mode")
    require(options["entry"] in {"develop", "review"}, "Unknown workflow entry")
    require(options["target"] is None or options["target"] in TARGETS, "Unknown delivery target")
    require(isinstance(options["isolation"], str) and options["isolation"] in {"auto", "checkout", "worktree"}, "Unknown isolation mode")
    require(isinstance(options["integration_position"], str) and options["integration_position"] in {"before_push", "after_push"}, "Unknown integration position")
    require(type(options["knowledge_approval"]) is bool, "knowledge_approval must be boolean")
    require(options["domain"] in DOMAINS, "Unknown project domain")
    bindings = options["capabilities"]
    require(isinstance(bindings, dict) and set(bindings) <= set(CAPABILITY_STAGES), "Unknown capability slot")
    for provider in bindings.values():
        identifier(provider)  # Logical names, never machine-specific paths.
    options["capabilities"] = {**workflow_defaults()["capabilities"], **bindings}
    require(isinstance(options["stages"], dict) and set(options["stages"]) <= SELECTABLE,
            "Only design, audit, test design, design approval, interfaces, integration and knowledge are selectable")
    require(all(type(flag) is bool for flag in options["stages"].values()), "Stage selections must be boolean")
    return options


def resolve_workflow(config: dict, overrides: dict | None = None) -> dict:
    options = workflow_options(config.get("workflow", {}))
    overrides = overrides or {}
    options = workflow_options({**options, **overrides,
                                "stages": {**options["stages"], **overrides.get("stages", {})},
                                "capabilities": {**options["capabilities"], **overrides.get("capabilities", {})}})
    profile = options["profile"]
    target = options["target"] or ("deployed" if profile == "release" else "local")
    enabled = {s: s in CORE for s in STAGES}
    enabled.update(design=profile in {"standard", "release"}, design_audit=profile in {"standard", "release"},
                   test_design=profile in {"standard", "release"}, design_approval=profile == "release",
                   integration=bool(config["stage_checks"].get("integration")))
    enabled.update(options["stages"])
    enabled.update(push=target != "local", pr=target in {"pr", "merged", "deployed"},
                   monitor=target in {"merged", "deployed"}, release=target == "deployed",
                   deploy=target == "deployed")
    if options["entry"] == "review":
        require(profile == "light", "Existing-change review requires the light profile")
        before_review = STAGES[:STAGES.index("review")]
        require(not any(options["stages"].get(s) for s in before_review),
                "Existing-change review cannot select development stages")
        enabled.update(dict.fromkeys(before_review, False))
    require(not enabled["design_audit"] or enabled["design"], "Design audit requires the design stage")
    require(not enabled["design_approval"] or enabled["design"] or profile == "codex",
            "Design audit and approval require the design stage")
    require(not enabled["integration"] or options["integration_position"] != "after_push" or target != "local",
            "Integration after push requires a remote delivery target")
    order = list(STAGES)
    if options["integration_position"] == "after_push":
        index = order.index("integration")
        order[index:index + 2] = ["push", "integration"]
    return {**options, "target": target, "enabled": enabled, "order": order}


def validate_command(spec: Any, label: str, *, adapter: bool = False) -> None:
    require(isinstance(spec, dict), f"{label} must be an object")
    require(set(spec) <= ({"argv", "timeout_seconds", "effect"} if adapter else {"argv", "timeout_seconds", "reuse"}),
            f"Unknown command option in {label}")
    argv = spec.get("argv")
    require(isinstance(argv, list) and bool(argv), f"{label}.argv must be a nonempty array")
    for arg in argv:
        require(isinstance(arg, str) and "\x00" not in arg, f"Invalid argv in {label}")
    nonempty(argv[0], f"{label}.argv[0]")
    timeout = spec.get("timeout_seconds", 300)
    require(type(timeout) is int and 1 <= timeout <= 86400, f"Invalid timeout in {label}")
    if "reuse" in spec:
        reuse = spec["reuse"]
        required = {"context_files", "max_age_seconds", "assumptions"}
        require(isinstance(reuse, dict) and required <= set(reuse) <= required | {"across_stages"},
                f"{label}.reuse requires context_files, max_age_seconds and assumptions")
        strings(reuse["context_files"], f"{label}.reuse.context_files", empty=True)
        nonempty(reuse["assumptions"], f"{label}.reuse.assumptions (why inputs are deterministic)")
        require(type(reuse.get("across_stages", False)) is bool, "reuse.across_stages must be boolean")
        require(type(reuse["max_age_seconds"]) is int and 1 <= reuse["max_age_seconds"] <= 86400,
                f"Invalid reuse age in {label}")
    if adapter:
        require(spec.get("effect") in {"read", "local", "external"},
                f"{label}.effect must be read, local or external")


def validate_config(data: Any) -> dict:
    require(isinstance(data, dict) and data.get("schema_version") == CONFIG_SCHEMA,
            "Unsupported project configuration schema_version (expected 2); no automatic conversion")
    require(not (set(data) - set(default_config())), "Unknown project configuration key")
    config = {**default_config(), **data}
    if config["base_ref"] is not None:
        nonempty(config["base_ref"], "base_ref")
        require(not config["base_ref"].startswith("-"), "base_ref cannot start with '-' ")
    for field in ("max_attempts", "parallel_max", "check_timeout_seconds", "review_max_age_seconds"):
        require(type(config[field]) is int and config[field] > 0, f"{field} must be a positive integer")
    require(config["parallel_max"] <= 64, "parallel_max cannot exceed 64")
    for key in ("checks", "stage_checks", "adapters"):
        require(isinstance(config[key], dict), f"{key} must be an object")
    for name, spec in config["checks"].items():
        identifier(name)
        validate_command(spec, f"checks.{name}")
    require(set(config["stage_checks"]) <= {"review", "integration"}, "Invalid stage_checks stage")
    for stage, checks in config["stage_checks"].items():
        strings(checks, f"stage_checks.{stage}", empty=True)
        require(set(checks) <= set(config["checks"]), f"Unknown check in stage_checks.{stage}")
    for stage, spec in config["adapters"].items():
        require(stage in ADAPTER_STAGES, f"Unsupported adapter stage: {stage}")
        validate_command(spec, f"adapters.{stage}", adapter=True)
    config["workflow"] = workflow_options(config["workflow"])
    from .hosts import validate as validate_host
    config["host"] = validate_host(config["host"])
    resolve_workflow(config)
    return config


def module_waves(modules: Any) -> list[list[str]]:
    require(isinstance(modules, list) and bool(modules), "intake.details.modules must not be empty")
    graph = {}
    for module in modules:
        require(isinstance(module, dict), "Each module must be an object")
        mid = identifier(module.get("id"))
        require(mid not in graph, f"Duplicate module: {mid}")
        deps = strings(module.get("depends_on", []), f"{mid}.depends_on", empty=True)
        require(mid not in deps, f"Module {mid} depends on itself")
        graph[mid] = set(deps)
    known = set(graph)
    for mid, deps in graph.items():
        require(deps <= known, f"Unknown dependencies for {mid}: {sorted(deps - known)}")
    waves, done = [], set()
    while len(done) < len(graph):
        wave = sorted(mid for mid, deps in graph.items() if mid not in done and deps <= done)
        require(wave, "Module dependencies contain a cycle")
        waves.append(wave)
        done.update(wave)
    return waves
