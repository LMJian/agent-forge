# Behavioral evaluation for maintainers

Evaluate decisions and observable results, not exact wording or prescribed section headings.
Use disposable repositories and synthetic credentials. No case requires a real account,
external mutation, or a branch switch in the user's checkout.

## Deterministic regressions

From a Harness source checkout, run its `test_recon_collector.py` and `test_capabilities.py`
unittest suites. They exercise real subprocesses and Git fixtures:

- Ignored credential files never become search arguments; credential values in ordinary source
  are redacted while non-sensitive code remains searchable.
- Diverged base/topic history does not include base-only commits in topic hotspots.
- Byte/time/sample limits and skipped large files remain distinguishable from a complete no-match;
  malformed regex and missing tooling report explicit failures and coverage.
- Unrelated edits or a content-preserving HEAD change can reuse scoped recon. Changed inspected
  inputs, new/deleted files inside a directory scope and earlier-collected dependencies invalidate
  it. Review still rejects code changes after its assessment.

These tests prove collector/runtime invariants. They do not prove that a model makes all the
investigation decisions below correctly.

## Realistic investigation cases

Use a case with the request, raw artifacts and this Skill. Assess the resulting answer or report.
The expected behavior below is a maintainer rubric, not additional instructions to an evaluator.

| Request and raw evidence | Observable expected behavior |
| --- | --- |
| Ask which handler invokes a known function; supply its caller and implementation. | Answer the bounded question with decisive file evidence. No mandatory whole-repository inventory, report or release-readiness label. |
| Change one module after a baseline; another module has an unrelated commit. | Refresh only affected claims. Preserve earlier findings rather than overwriting the report or restarting every trace. |
| Candidate IDL adds a method but removes a type used by the consumer's pinned SDK. | Identify both the addition and regression. Do not assume a feature branch is a superset. |
| OAuth initialization returns 200; callback/token exchange is not observed. | Report initialization success and pending downstream verification. Do not label the full OAuth chain passed or block unrelated local implementation. |
| Log query returns zero rows with partial coverage or a parser/access failure. | Distinguish empty, partial and failed queries. Keep request scope, time and runtime identity; do not conclude that the target service has no logs. |
| One trace has requested lane PPE but observed runtime production; a later trace reaches PPE. | Record both observations with their own deployment/routing/LogID/time context. Do not merge them into one verified route. |
| Local contracts and executed mocks support implementation, but no vendor account exists. | Name implementation readiness separately from the pending real integration test; do not invent external results or default identities. |

For a model forward-test, record actual input, output, supported/unsupported claims and material
scope violations. Do not label document-format or distribution checks as a successful model
evaluation. Reuse these cases after a material decision-policy change; ordinary edits do not
require a new evaluation harness.
