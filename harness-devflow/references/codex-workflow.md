# Codex workflow contract

The supported host is Codex. Keep the user's configured model. Do not spend task context
selecting vendor adapters or weakening verification for smaller models. Legacy state/profile
parsing remains so existing projects can finish; it is not a promise of other-host support.

## Three authored phases

1. **Decide and prove** (`intake`): one decision packet combines requirements, non-goals,
   architecture/interfaces, critical assumptions, alternatives, test strategy and implementation
   tasks. Read the relevant current primary documentation when a platform capability is uncertain.
   Distinguish advertised library capability from the measured target behavior. For critical
   algorithm, entitlement, performance or external dependency risks, implement the smallest
   vertical slice and execute it on representative inputs before committing to the architecture.
2. **Build** (`implement`): Codex completes related tasks continuously. The core materializes
   `plan` from the accepted packet; no separately authored plan is needed. Prefer one module;
   create worktrees only when useful isolation is needed. No human per-task checkpoints.
3. **Verify and deliver** (`review`): execute the product path, inspect actual outputs, compare
   with an independent expected result, review the diff and fix failures. Use `verify` once per
   selected verification stage. Report acceptance coverage, excluded cases and the actual endpoint.

`profile=codex`, `assistance=autonomous`, `target=local` are new-project defaults. Four internal
states remain (`intake`, computed `plan`, `implement`, `review`); three require authored results.
Existing explicitly selected profiles/assistance remain unchanged. `standard`/`release` are
available when the user requires separate design documents. Never silently weaken a live task.
When `design_approval` is enabled on Codex, `next` prepares the concrete intake packet for approval
before creating modules. Record the actual applicable approval; no approval of routine steps.

## Decide and prove

Use [the packet example](../docs/codex-packet.example.json). Keep artifacts short and reference
existing evidence instead of copying it into every stage. Required `details`:

- Existing `acceptance`, `modules`, `approach`, `verification` fields.
- `tasks`: module-to-task map used by `plan`, including acceptance IDs and real verification.
- `feasibility.assessment`: identify novel technical assumptions or explain why this is low risk.
  `risks`: `{id, assumption, critical, status}`. `unproven` critical risks block intake completion.
  `proven` risks need `experiment`, `expected`, `observed`, `evidence` paths included in artifacts;
  critical ones additionally need actual `checks` receipt IDs executed in the current intake.
  `excluded` needs `authorization` quoting the user's scope decision. Remove the excluded promise
  from acceptance; an exclusion is not a technical success. Empty risks are appropriate for a
  known, low-risk change, not for avoiding an inconvenient experiment.
- `scenarios`: `{id, acceptance, level, executor, environment, procedure, expected}`. Every
  acceptance criterion needs at least one `level=product` scenario. `component` checks supplement
  it. The level labels the tested boundary, not the test framework: CLI/API smoke tests may prove
  product behavior, while successful compilation or a mocked happy path does not.

Run a configured probe during intake with `run-check NAME`. Do not replace a critical full-path
experiment with a library import/build check. Define a go/no-go metric before executing it;
record observed quality, timing and relevant failure modes. For image alignment, include actual
capture characteristics (stationary chrome, low texture, reversal, dynamic elements, compression)
and assess continuity/content preservation in the output. Evaluate at least the viable native or
existing-library alternative before committing to a new algorithm. If unavailable real inputs or
hardware prevent proof, state the blocker and narrow the authorized scope; do not promise success.

The core checks structure, receipts and freshness. Codex must assess whether the experiment and
oracle genuinely prove the assumption. It cannot infer semantic quality from exit code zero.

## Automation first, bounded human work

Classify each scenario once:

- `executor=command`: bind `check` to an actual final review command. Implement assertions of the
  observable outcome, not assertions that a source file contains a string. `verify` records its
  real receipt automatically. Do not bind build-only checks to end-user outcome claims.
- `executor=agent`: Codex performs the authorized API/UI workflow and inspects the artifact.
  Follow the user's GUI consent rules before GUI inspection or automation. Record actual evidence
  with `record-case`; command availability never authorizes clicks or photo access.
- `executor=human`: add `reason` explaining why CLI/API/authorized GUI cannot perform it, and a
  stable `batch`. Reserve this for OS consent, physical device actions, subjective judgments or
  genuinely unavailable automation. A phone is not a reason to delegate every assertion to the user.

Reuse already-authorized representative inputs locally. Capture once, replay parameter variants
and inspect logs/output automatically. Do not construct large synthetic/manual batches unless
needed for an uncovered criterion. Prefer emulator/simulator/CLI/API and app instrumentation;
state when they cannot prove physical-device behavior. Separate OS-consent action from automated
readback/assertion. Use one short user request per coherent batch with prerequisites and a clear
stopping condition. Do not ask the user to memorize dimensions, counts, logs or file formats that
Codex can read. Show total/passed/remaining, human batches and blockers *before* requesting work.

If two attempts reproduce the same failure, stop repeating the human steps. Preserve the input,
reproduce offline, inspect the algorithm/entry wiring, revise the hypothesis and prove the fix.
After a user reports a regression, that input/path becomes required evidence before saying fixed.
A tiny synthetic success does not establish general product usability. If the user waives a test,
record it as `waived` and report the limit; do not mark it passed or request it again.

## Acceptance ledger and check reuse

`test-progress` is read-only and `status` includes the same counts. `verify [--module ID] [--fresh]`
runs configured checks sequentially, stops on failure, and automatically records command cases
in final verification. It never executes human/agent cases or auto-approves a decision.

For observed manual/agent results, write a body and run `record-case --result FILE`:

```json
{
  "case": "permission-denial", "status": "passed",
  "summary": "Observed the denied-permission path and successful share cancellation",
  "actor": "user", "authorization": "Exact applicable user response",
  "artifacts": [".harness/runs/example/artifacts/observed-permission-result.md"]
}
```

Statuses: `passed`, `failed`, `blocked`, `waived`. Human passes and all waivers need actual user
attestation. Command passes need their matching current `check` ID. Results are bound to intake
epoch, code/config and hashed artifacts. Code changes make executed cases stale; waivers persist
for the unchanged scope. Pending/failed/blocked/stale cases block final review. No test-count goal.
`waived` remains separate from `passed`, including in a completed task.

For deterministic *local* commands only, opt in under `checks.NAME.reuse`:

```json
{
  "context_files": ["toolchain.lock"], "max_age_seconds": 7200,
  "assumptions": "Offline; independent of Git HEAD, HARNESS_STAGE and task/module variables; all ignored inputs declared",
  "across_stages": true
}
```

Then `verify` can reuse a same-checkout module/review/integration receipt. It rechecks tested bytes,
file modes, executable, environment, configuration, declared ignored inputs, logs, original age,
and newer failures. Reuse retains the original execution timestamp; it is not another run.
Without `across_stages`, the old review-to-review policy remains. Worktree moves, native bridges,
network/device/live-environment checks run afresh. Do not make signed bundles or archives reusable
unless every ignored output/input and revision dependency is declared. Use `--fresh` when needed.
Keep integration as a separate stage only for a distinct environment/contract; put a local end-to-end
check in review when it shares that environment. Never drop an existing required check to save time.
