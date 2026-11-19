# Bounded work and minimal changes

Use existing intake/review and configured checks: no new stage, service SDK or mandatory
load-test platform. This contract applies to all profiles and existing-change `start-review`.

## Assess the actual diff

Intake `details.engineering` assesses six areas. Review can reuse that accepted assessment
when unchanged; supply `details.engineering` only for corrections or `start-review` without intake.
Each area has `reason` and `checks`
(configured final review names). Empty checks mean not applicable and need a concrete reason.
`minimal_change` always needs a behavioral regression check. Review can add checks but cannot
drop accepted intake checks or change their accepted budgets without reopening intake.
One check can cover several areas.

```json
{
  "io": {"reason": "Bound calls and bytes per operation as unrelated records grow", "checks": ["work-budget"]},
  "retry": {"reason": "No retry or asynchronous delivery changes", "checks": []},
  "performance": {"reason": "Existing bounded constant-work operation", "checks": []},
  "loops": {"reason": "No iteration or background work changes", "checks": []},
  "data_size": {"reason": "Record shape, cardinality and retention unchanged", "checks": []},
  "minimal_change": {"reason": "Retain public success and error contracts", "checks": ["contract-regression"]}
}
```

For applicable areas, identify normal, peak and boundary workloads and project-derived
bounds before implementation. Dimensions include records, fanout, batch size, concurrency,
replicas, retention and retry/redelivery depth. Keep the reasoning beside existing acceptance
and scenarios; do not create duplicate reports or require a large benchmark for a small edit.

| Area | Review and executable evidence |
| --- | --- |
| `io` | Count calls **and bytes** across the logical operation, including storage/CAS, RPC and MQ. Compare small/large unrelated datasets. Check N+1, aggregate rewrites, hot roots and redundant state. |
| `retry` | Map SDK, business, broker and scheduler attempts together. Assert total attempts, fixed deadlines, cancellation, permanent errors and final side effects under response loss/restart. Justify each dedup layer and its storage cost. |
| `performance` | Measure representative latency/throughput, allocations/memory or deterministic work as appropriate. Compare baseline and candidate under the same conditions; declare noise/repeat policy. Work counts do not prove runtime latency/capacity. |
| `loops` | Bound work per iteration and across replicas. Prove cursor progress and cancellation with empty input, bad entries and stuck cursors. Paging alone does not bound total scans or scheduling. |
| `data_size` | Measure serialized bytes, cardinality, root/index size and update/cleanup cost. Test retention/expiry and contention when changed. Small pages do not prove a bounded root or logical collection. |
| `minimal_change` | Tie behavior changes to requirements or necessary fixes; test retained contracts and existing optimizations. Verify callers before removing code/config. New retries, dedup, caches, calls, switches or compatibility need a concrete requirement/failure. Diff size alone proves nothing. |

Static searches suggest risks; they do not establish failure or absence. Assess the actual
diff, workload, oracle and instrumentation. Source-string assertions, coverage percentages
or mocked happy paths do not prove these properties. Replay known failures against an
independent expected result; exercise baseline counterexamples when available without
switching development branches/worktrees without consent.

## Declare and measure budgets

Only relevant configured checks need `budget`. Example check fragment (illustrative numbers,
not universal defaults):

```json
{
  "argv": ["python3", "tests/check_work_budget.py"],
  "proof": "component",
  "budget": {
    "workload": {"records": 1000, "concurrency": 16},
    "inputs": ["tests/data/workload.json"],
    "metrics": {
      "normal.writes": {"area": "io", "unit": "operations/logical-operation", "max": 2},
      "normal.write_bytes": {"area": "io", "unit": "bytes/logical-operation", "max": 4096},
      "duplicate.writes": {"area": "io", "unit": "operations/logical-operation", "max": 0}
    }
  }
}
```

An applicable resource area needs at least one budget metric with its own `area`; its other
behavioral regression checks need not output metrics. Static/build checks
cannot satisfy engineering assessments. Use existing adapters or test instrumentation,
with no new business runtime dependency. The command writes one JSON object to the unique
`HARNESS_METRICS_FILE` path; ordinary stdout/stderr stay logs:

```json
{
  "workload": {"records": 1000, "concurrency": 16},
  "measurements": {
    "normal.writes": {"value": 2, "unit": "operations/logical-operation"},
    "normal.write_bytes": {"value": 2048, "unit": "bytes/logical-operation"},
    "duplicate.writes": {"value": 0, "unit": "operations/logical-operation"}
  }
}
```

Bounds are inclusive `min` and/or `max`. Project checks can compute ratios/aggregate retry
cost from observed baseline/candidate values; retain raw measurements and environment in
logs/artifacts. Determine budgets from requirements, baseline and dependency capacity.
Never relax failed budgets merely to pass; scope/requirement changes need concrete evidence
and an explicit decision. Do not include secrets or raw private payloads.

Exit zero cannot override absent/oversized/malformed reports, missing metrics, wrong units
or workloads, non-finite values or breached bounds. Limits: 1 MiB/report, 128 bounds and 64
input files. `inputs` declares additional data/config (including ignored files); they must
exist, stay unchanged during execution and match at completion/reuse/delivery. Existing
code/config/report fingerprints still apply. An old report is not a fresh run; live checks
need fresh environment evidence.

`verify-plan` shows budgets without executing checks. Receipts retain measurements, limits
and failures. Missing dependencies remain blocked; explicit exclusions are not passes.
Local/pushed completion does not establish deployed readiness: prove real capacity,
permissions and final effects in the required environment.
