"""Reject measured regressions through the real CLI, even when functional tests pass."""
import copy
import math
import sys
import unittest
from pathlib import Path

from harness import engineering, gates, runner
from harness.engine import Workflow
from harness.model import HarnessError, validate_config
from harness.storage import atomic_json, read_json
from harness.verification import plan, verify
import test_host_execution as support
from test_workflow import RepoCase, engineering_assessment


# A disposable service-like fixture. Mutations retain the public result but change
# actual work, retry behavior, progress, serialized size or a retained contract.
FIXTURE = '''import json, os, threading
from pathlib import Path

mode = Path('.workload').read_text().strip()
while mode == 'hang': pass
n = 32
counts = dict(reads=0, writes=0, write_bytes=0, attempts=0, comparisons=0)
def write():
    counts['writes'] += 1
    payload = json.dumps(list(range(n * 100))) if mode == 'io_bytes' else '{}'
    counts['write_bytes'] += len(payload.encode())
def read(): counts['reads'] += 1
def downstream():
    counts['attempts'] += 1
    raise TimeoutError('response lost')

for _ in range(n if mode == 'io' else 1): write()
for _ in range(n if mode == 'unrelated' else 1): read()
for _ in range(3):
    for _ in range(3 if mode == 'retry' else 1):
        try: downstream()
        except TimeoutError: pass
ticks, deadline = 0, 3
while ticks < deadline and ticks < 16:
    ticks += 1
    if mode == 'deadline_reset': deadline = ticks + 3
for i in range(n):
    for _ in range(n if mode == 'performance' else 1): counts['comparisons'] += 1
cursor = steps = 0
while cursor < n and steps < 64:
    steps += 1
    if mode != 'loop': cursor += 1
# All pages fit. An unbounded root still breaks the large-object budget.
pages = [list(range(4)) for _ in range(n)]
assert all(len(json.dumps(page).encode()) <= 128 for page in pages)
root = json.dumps(list(range(n * 100)) if mode == 'data_size' else ['page-1'])
legacy_locks = 0
lock = threading.RLock()
for _ in range(3 if mode == 'minimal_change' else 1):
    with lock: legacy_locks += 1
assert sum(range(3)) == 3  # Feature behavior stays correct in every mutation.
values = dict(counts, elapsed=ticks, steps=steps, remaining=n-cursor, root_bytes=len(root.encode()), legacy_locks=legacy_locks)
if mode == 'missing_report': raise SystemExit(0)
report = {'workload': {'records': n, 'attempt_limit': 3}, 'measurements': {
    name: {'value': value, 'unit': 'bytes' if name in ('root_bytes', 'write_bytes') else 'count'}
    for name, value in values.items()}}
if mode == 'missing_metric': del report['measurements']['writes']
if mode == 'unit': report['measurements']['writes']['unit'] = 'ms'
if mode == 'nan': report['measurements']['writes']['value'] = float('nan')
if mode == 'boolean': report['measurements']['writes']['value'] = True
if mode == 'workload': report['workload']['records'] = 1
Path(os.environ['HARNESS_METRICS_FILE']).write_text(json.dumps(report))
'''


def budget():
    limits = {"writes": 1, "write_bytes": 32, "reads": 1, "attempts": 3, "elapsed": 3, "comparisons": 32,
              "steps": 32, "remaining": 0, "root_bytes": 128, "legacy_locks": 1}
    areas = {"writes": "io", "write_bytes": "io", "reads": "io", "attempts": "retry", "elapsed": "retry", "comparisons": "performance",
             "steps": "loops", "remaining": "loops", "root_bytes": "data_size", "legacy_locks": "minimal_change"}
    return {"workload": {"records": 32, "attempt_limit": 3}, "inputs": [".workload"],
            "metrics": {key: {"area": areas[key], "unit": "bytes" if key in {"root_bytes", "write_bytes"} else "count", "max": value}
                        for key, value in limits.items()}}


class EngineeringTests(RepoCase):
    cli = support.PortableExecutionTests.cli

    def setUp(self):
        super().setUp()
        self.flow.abort("Review service work budgets")
        self.write(".gitignore", "__pycache__/\n*.pyc\n.workload\n")
        self.write(".workload", "good")
        self.write("workload.py", FIXTURE)
        config = read_json(self.root / ".harness/project.json")
        config["checks"]["cost"] = {"argv": [sys.executable, "workload.py"], "budget": budget()}
        config["stage_checks"] = {"review": ["unit", "cost"], "integration": []}
        config["workflow"] = {}
        atomic_json(self.root / ".harness/project.json", config)
        self.commit("Configure bounded service fixture")
        self.flow = Workflow(self.root, "engineering")
        self.cli("start-review", "--goal", "Preserve behavior with bounded work", "--base", "main",
                 "--acceptance", "Return the public result without exceeding resource budgets")
        self.cli("next")

    def assessment(self):
        return {area: {"reason": "Measured service work and retained ordinary contract at records=32",
                       "checks": ["cost"]} for area in engineering.AREAS}

    def complete(self, assessment=None):
        state = self.flow.load()
        return self.flow.complete("review", str(self.report("review", details={
            "engineering": self.assessment() if assessment is None else assessment},
            checks=[r["id"] for r in state["runs"] if r["status"] == "passed" and
                    r["stage"] == "review" and r["epoch"] == state["stages"]["review"]["epoch"]])))

    def mode(self, mode):
        self.write(".workload", mode)

    def test_functional_success_does_not_hide_each_measured_regression(self):
        self.assertEqual(runner.run(self.flow, "check", "unit")["status"], "passed")
        # Reopen the same stage between independent faults, retaining the configured
        # retry budget rather than raising it to make the tests pass.
        for mode, metric in [("io", "writes"), ("io_bytes", "write_bytes"), ("unrelated", "reads"),
                             ("retry", "attempts"), ("deadline_reset", "elapsed"),
                             ("performance", "comparisons"), ("loop", "remaining"),
                             ("data_size", "root_bytes"), ("minimal_change", "legacy_locks")]:
            with self.subTest(mode=mode):
                self.mode(mode)
                result = self.cli("verify", expected=1)
                self.assertEqual(result["status"], "failed")
                receipt = self.flow.load()["runs"][-1]
                self.assertEqual(receipt["exit_code"], 0)
                self.assertIn(metric, receipt["error"])
                with self.assertRaisesRegex(HarnessError, "failed check|Missing required"):
                    self.complete()
                self.flow.reopen("review", "Next independent regression fixture")
                self.cli("next")

    def test_missing_or_malformed_metrics_never_pass_on_exit_zero(self):
        for mode in ("missing_report", "missing_metric", "unit", "nan", "boolean", "workload"):
            with self.subTest(mode=mode):
                self.mode(mode)
                receipt = runner.run(self.flow, "check", "cost")
                self.assertEqual((receipt["exit_code"], receipt["status"]), (0, "failed"))
                self.flow.reopen("review", "Next independent malformed report")
                self.cli("next")

    def test_good_budget_finishes_without_extra_stages_or_commands(self):
        result = verify(self.flow)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(self.complete()["status"], "complete")
        self.assertEqual(self.flow.status()["active_stages"], ["review"])
        self.assertEqual(len(self.flow.load()["runs"]), 2)

    def test_missing_assessment_unknown_check_and_build_only_cannot_complete(self):
        verify(self.flow)
        assessments = [({}, "details.engineering"),
                       ({**self.assessment(), "io": {"reason": "Measured", "checks": ["unknown"]}}, "configured"),
                       ({**self.assessment(), "minimal_change": {"reason": "Small diff", "checks": []}}, "regression check"),
                       ({**self.assessment(), "io": {"reason": "Function passed", "checks": ["unit"]}}, "measured check budget")]
        for assessment, error in assessments:
            with self.subTest(error=error), self.assertRaisesRegex(HarnessError, error):
                self.complete(assessment)
        state = self.flow.load()
        state["config"]["checks"]["cost"]["proof"] = "build"
        with self.assertRaisesRegex(HarnessError, "behavioral evidence"):
            engineering.validate_assessment(state, {"engineering": self.assessment()})

    def test_not_applicable_is_explicit_and_cannot_drop_planned_checks(self):
        assessment = engineering_assessment()
        engineering.validate_assessment(self.flow.load(), {"engineering": assessment})
        assessment["io"]["reason"] = " "
        with self.assertRaisesRegex(HarnessError, "nonempty"):
            engineering.validate_assessment(self.flow.load(), {"engineering": assessment})
        with self.assertRaisesRegex(HarnessError, "dropped accepted checks"):
            engineering.validate_assessment(self.flow.load(), {"engineering": engineering_assessment()}, self.assessment())

    def test_changed_ignored_input_or_metrics_invalidates_completed_review(self):
        verify(self.flow)
        self.complete()
        self.mode("io")
        self.assertEqual(self.flow.status()["status"], "stale")
        with self.assertRaisesRegex(HarnessError, "stale"):
            gates.gate(self.flow)
        self.mode("good")
        receipt = self.flow.load()["runs"][-1]
        Path(receipt["stdout"]).with_name("metrics.json").write_text("{}")
        self.assertEqual(self.flow.status()["status"], "stale")

    def test_verify_plan_exposes_budget_without_executing_it(self):
        before = len(self.flow.load()["runs"])
        cost = next(c for c in plan(self.flow)["checks"] if c["name"] == "cost")
        self.assertEqual(cost["budget"], budget())
        self.assertEqual(len(self.flow.load()["runs"]), before)

    def test_budget_configuration_rejects_invalid_bounds(self):
        original = self.flow.config
        for value in (True, math.inf, math.nan, "1"):
            with self.subTest(value=value), self.assertRaisesRegex(HarnessError, "finite"):
                config = copy.deepcopy(original)
                config["checks"]["cost"]["budget"]["metrics"]["writes"]["max"] = value
                validate_config(config)

    def test_unrelated_budget_metric_cannot_cover_a_different_area(self):
        state = copy.deepcopy(self.flow.load())
        for bound in state["config"]["checks"]["cost"]["budget"]["metrics"].values():
            bound["area"] = "io"
        with self.assertRaisesRegex(HarnessError, "own area"):
            engineering.validate_assessment(state, {"engineering": self.assessment()})

    def test_resource_area_can_share_budget_and_ordinary_regression_checks(self):
        assessment = self.assessment()
        assessment["io"]["checks"] = ["unit", "cost"]
        engineering.validate_assessment(self.flow.load(), {"engineering": assessment})
        verify(self.flow)
        self.assertEqual(self.complete(assessment)["status"], "complete")

    def test_input_change_during_execution_is_a_failed_check(self):
        config = read_json(self.root / ".harness/project.json")
        config["checks"]["cost"]["argv"] = [sys.executable, "-c",
            "exec(open('workload.py').read()); open('.workload', 'w').write('io')"]
        atomic_json(self.root / ".harness/project.json", config)
        self.flow.sync_config("Exercise a check that changes its declared inputs")
        self.cli("next")
        receipt = runner.run(self.flow, "check", "cost")
        self.assertEqual(receipt["budget"]["status"], "passed")
        self.assertEqual(receipt["status"], "failed")
        self.assertIn("Artifact changed", receipt["error"])

    def test_budget_check_reuse_does_not_hide_changed_data(self):
        from harness.reuse import reuse
        config = read_json(self.root / ".harness/project.json")
        config["checks"]["cost"]["reuse"] = {"context_files": [], "max_age_seconds": 7200,
            "assumptions": "Offline fixture; additional workload is pinned by budget.inputs"}
        atomic_json(self.root / ".harness/project.json", config)
        self.flow.sync_config("Exercise deterministic metric reuse")
        self.cli("next")
        receipt = runner.run(self.flow, "check", "cost")
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(reuse(self.flow, "cost", receipt["id"])["reused_from"], receipt["id"])
        self.mode("io")
        with self.assertRaisesRegex(HarnessError, "Artifact changed"):
            reuse(self.flow, "cost", receipt["id"])

    def test_nonterminating_work_is_stopped_by_existing_timeout(self):
        config = read_json(self.root / ".harness/project.json")
        config["checks"]["cost"]["timeout_seconds"] = 1
        atomic_json(self.root / ".harness/project.json", config)
        self.flow.sync_config("Bound an intentionally nonterminating fixture")
        self.cli("next")
        self.mode("hang")
        receipt = runner.run(self.flow, "check", "cost")
        self.assertTrue(receipt["timed_out"])
        self.assertEqual(receipt["status"], "failed")
        self.assertIn("timed out", receipt["error"])

    def test_report_and_input_limits_are_enforced(self):
        path = self.root / ".harness/oversized.json"
        path.write_bytes(b" " * (engineering.MAX_REPORT_BYTES + 1))
        with self.assertRaisesRegex(HarnessError, "1 MiB"):
            engineering.evaluate(budget(), path)
        for key in ("metrics", "inputs"):
            bad = budget()
            bad[key] = {str(i): {} for i in range(129)} if key == "metrics" else [str(i) for i in range(65)]
            with self.assertRaises(HarnessError):
                engineering.validate_budget(bad)
        for raw in (b"[]", b"{broken", b""):
            path.write_bytes(raw)
            with self.assertRaises(HarnessError):
                engineering.evaluate(budget(), path)

    def test_integration_only_input_drift_blocks_delivery(self):
        self.write(".gitignore", (self.root / ".gitignore").read_text() + ".integration-workload\n")
        self.write(".integration-workload", "good")
        config = read_json(self.root / ".harness/project.json")
        check = copy.deepcopy(config["checks"]["cost"])
        check["budget"]["inputs"] = [".integration-workload"]
        check["argv"] = [sys.executable, "-c",
            "exec(open('workload.py').read().replace('.workload', '.integration-workload'))"]
        config["checks"]["integration-cost"] = check
        config["stage_checks"]["integration"] = ["integration-cost"]
        atomic_json(self.root / ".harness/project.json", config)
        self.flow.sync_config("Verify a distinct integration workload")
        self.flow.enter("review")
        verify(self.flow)
        self.complete()
        self.flow.enter("integration")
        receipt = runner.run(self.flow, "check", "integration-cost")
        self.assertEqual(receipt["status"], "passed")
        self.flow.complete("integration", str(self.report("integration", checks=[receipt["id"]])))
        self.assertEqual(self.flow.status()["status"], "complete")
        self.write(".integration-workload", "io")
        self.assertEqual(self.flow.status()["status"], "stale")
        with self.assertRaisesRegex(HarnessError, "stale"):
            gates.gate(self.flow)


class IntakeBudgetTests(RepoCase):
    def test_review_can_reuse_intake_assessment_without_duplicate_payload(self):
        self.to_review()
        receipt = runner.run(self.flow, "check", "unit")
        path = self.report("review", checks=[receipt["id"]])
        body = read_json(path)
        body.pop("details")
        atomic_json(path, body)
        self.assertEqual(self.flow.complete("review", str(path))["current_stage"], "integration")

    def test_missing_engineering_cannot_complete_intake(self):
        self.flow.enter("intake")
        path = self.report("intake", details={"acceptance": ["AC-1"],
            "modules": [{"id": "core", "acceptance": ["AC-1"]}]})
        body = read_json(path)
        del body["details"]["engineering"]
        atomic_json(path, body)
        with self.assertRaisesRegex(HarnessError, "details.engineering"):
            self.flow.complete("intake", str(path))

    def test_raising_accepted_budget_requires_reopening_intake(self):
        config = read_json(self.root / ".harness/project.json")
        check = config["checks"]["unit"]
        check["budget"] = {"workload": {"retained_api": "base.value"}, "inputs": [],
            "metrics": {"retained_value": {"area": "minimal_change", "unit": "value", "min": 1, "max": 1}}}
        check["argv"] = [sys.executable, "-c",
            "import json, os, unittest; from pathlib import Path; from base import value; "
            "result=unittest.TextTestRunner().run(unittest.defaultTestLoader.discover('tests')); "
            "assert result.wasSuccessful(); "
            "Path(os.environ['HARNESS_METRICS_FILE']).write_text(json.dumps({"
            "'workload': {'retained_api': 'base.value'}, 'measurements': {"
            "'retained_value': {'value': value(), 'unit': 'value'}}}))"]
        atomic_json(self.root / ".harness/project.json", config)
        self.commit("Configure accepted test budgets")
        self.flow.sync_config("Declare retained-behavior budget before intake")
        self.to_review()
        config["checks"]["unit"]["budget"]["metrics"]["retained_value"]["max"] = 100
        atomic_json(self.root / ".harness/project.json", config)
        self.flow.sync_config("Simulate an unjustified budget increase")
        self.flow.enter("review")
        receipt = runner.run(self.flow, "check", "unit")
        self.assertEqual(receipt["status"], "passed")
        with self.assertRaisesRegex(HarnessError, "budgets changed; reopen intake"):
            self.flow.complete("review", str(self.report("review", checks=[receipt["id"]])))


if __name__ == "__main__":
    unittest.main()
