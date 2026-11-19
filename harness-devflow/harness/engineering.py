"""Small, language-independent engineering assessments and measured check budgets."""
from __future__ import annotations

import json
import math

from .model import HarnessError, digest, nonempty, require, strings


AREAS = ("io", "retry", "performance", "loops", "data_size", "minimal_change")
MAX_REPORT_BYTES = 1024 * 1024


def number(value):
    return type(value) is int or (type(value) is float and math.isfinite(value))


def validate_budget(budget):
    require(isinstance(budget, dict) and set(budget) == {"workload", "metrics", "inputs"},
            "budget requires workload, metrics and inputs")
    require(isinstance(budget["workload"], dict) and budget["workload"], "budget.workload must describe representative inputs")
    strings(budget["inputs"], "budget.inputs", empty=True)
    require(len(budget["inputs"]) <= 64, "budget.inputs exceeds 64 files; narrow the check")
    metrics = budget["metrics"]
    require(isinstance(metrics, dict) and 0 < len(metrics) <= 128, "budget.metrics requires 1–128 measured bounds")
    for name, bound in metrics.items():
        nonempty(name, "metric name")
        require(isinstance(bound, dict) and {"unit", "area"} < set(bound) <= {"unit", "area", "min", "max"},
                "Metric bounds require area, unit and min and/or max")
        require(bound["area"] in AREAS, "Metric area must identify an engineering constraint")
        nonempty(bound["unit"], "metric.unit")
        for key in set(bound) - {"unit", "area"}:
            require(number(bound[key]), "Metric bounds must be finite numbers, not booleans")
        require(bound.get("min", -math.inf) <= bound.get("max", math.inf), "Metric minimum exceeds maximum")


def validate_assessment(state, details, planned=None):
    assessment = details.get("engineering")
    require(isinstance(assessment, dict) and set(assessment) == set(AREAS),
            "details.engineering must assess io, retry, performance, loops, data_size and minimal_change")
    final_checks = state["config"]["stage_checks"].get("review", [])
    for area, item in assessment.items():
        require(isinstance(item, dict) and set(item) == {"reason", "checks"},
                f"engineering.{area} requires reason and checks (empty only when not applicable)")
        nonempty(item["reason"], f"engineering.{area}.reason (changed boundary, workload or why not applicable)")
        names = strings(item["checks"], f"engineering.{area}.checks", empty=True)
        require(area != "minimal_change" or names, "minimal_change needs a preserved-behavior regression check")
        require(set(names) <= set(final_checks), f"engineering.{area} must use configured final review checks")
        for name in names:
            check = state["config"]["checks"][name]
            require(check.get("proof", "component") not in {"static", "build"},
                    f"engineering.{area} needs behavioral evidence at its check boundary, not static/build checks")
        if names and area != "minimal_change":
            require(any(bound["area"] == area for name in names
                        for bound in state["config"]["checks"][name].get("budget", {}).get("metrics", {}).values()),
                    f"engineering.{area} needs a measured check budget metric for its own area")
        if planned:
            require(set(planned[area]["checks"]) <= set(names),
                    f"engineering.{area} dropped accepted checks; reopen intake to change the scope")
    return assessment


def budget_digest(state, assessment):
    """Pin accepted resource bounds without duplicating their definitions in reports."""
    names = {name for item in assessment.values() for name in item["checks"]}
    return digest({name: state["config"]["checks"][name].get("budget") for name in sorted(names)})


def evaluate(budget, path):
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_REPORT_BYTES + 1)
        require(len(raw) <= MAX_REPORT_BYTES, "Budget report exceeds 1 MiB")
        report = json.loads(raw)
    except (OSError, ValueError) as error:
        raise HarnessError(f"Budget check must write valid JSON to HARNESS_METRICS_FILE: {error}") from error
    require(isinstance(report, dict), "Metric report must be one JSON object")
    require(set(report) == {"workload", "measurements"}, "Metric report requires workload and measurements")
    require(digest(report["workload"]) == digest(budget["workload"]), "Measured workload differs from the declared budget workload")
    actual = report["measurements"]
    require(isinstance(actual, dict) and set(actual) == set(budget["metrics"]),
            "Metric report must contain every declared metric, with no undeclared metrics")
    results = []
    for name, bound in budget["metrics"].items():
        sample = actual[name]
        require(isinstance(sample, dict) and set(sample) == {"value", "unit"}, "Each measurement needs value and unit")
        require(number(sample["value"]), f"Metric {name} must be a finite number, not a boolean")
        require(sample["unit"] == bound["unit"], f"Metric {name} unit does not match its budget")
        value = sample["value"]
        passed = bound.get("min", -math.inf) <= value <= bound.get("max", math.inf)
        results.append({"metric": name, "value": value, **bound, "status": "passed" if passed else "failed"})
    return {"workload": report["workload"], "metrics": results,
            "status": "passed" if all(r["status"] == "passed" for r in results) else "failed"}
