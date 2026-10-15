# Recon Output

The output should support the next decision. Scale its form to the scope and audience; do not produce a fixed audit package for every edit.

## Answer or durable baseline

For a bounded standalone fact/history question, a direct answer with conclusion, revision-scoped evidence and unresolved limits can be sufficient. Do not force a report, target-change table or readiness label onto that answer. If the user asks for a report/handoff, substantial findings need preservation, or design/implementation needs a baseline, use the report contract below. Harness capability requests retain their required report, phase/readiness and result artifacts.

Reuse applicable earlier reports for follow-ups. Verify only claims affected by relevant source, dependency, configuration or runtime changes; unchanged evidence does not need to be recopied into a new report. Answer directly when there is no material new finding. Append dated discoveries without rewriting the baseline, or create a distinct baseline for a materially different scope/version.

## Location and discoverable entry

Use the Harness request's `output_directory`, the user's selected output directory or the project's
artifact convention. Without any of these, write
`.artifacts/brownfield-recon/<branch-key>/<run-id>/report.md` inside the consumer repository. A
Harness-managed report lives at `.harness/runs/<task>/artifacts/capabilities/<id>/report.md`; it
follows this same contract so a later standalone design session can read it, and a standalone
report under `.artifacts/` can likewise be supplied to a Harness task as an input report. The branch
key is a safe directory label, not a substitute for the actual Git branch recorded below. Use a task
key for non-Git sources. Keep each baseline under a distinct run ID; never silently overwrite an old
report to make it describe the new code. An existing project report name or directory remains valid.

When a report is produced, it is the entrypoint; a separate manifest, global index or collector JSON
is not required. A reader should be able to identify the right report from its opening context
without reading every inventory or remembering the producing conversation. A factual/history
report can focus on findings, revision-scoped evidence and limits; the development fields below
apply when preparing a change.

## Default: one short baseline

Before implementation, write a compact `report.md` containing:

- Task/goal and target requirement/design source, repository identity, and affected repository-relative paths or contracts.
- Actual branch, baseline commit/source version, capture time and relevant working-tree state. Record changed/untracked files and captured evidence or content digests when conclusions depend on uncommitted bytes; HEAD alone does not identify them.
- Deployment/compatibility requirements and any limit on which repositories or components were investigated.
- Phase-specific readiness and a short reason.
- A change table with concrete evidence and validation behavior.
- Only the gaps that remain relevant, stating whether they block this phase or belong to later verification.

| Current behavior and evidence | Required target | Retain / replace / remove | Affected files | Validation scenario |
| --- | --- | --- | --- | --- |

Use concise prose when a table would add no clarity. Avoid empty sections, duplicate system descriptions and a separate question file when no questions exist. A collector-generated `baseline-evidence.json` is useful when discovery is broad; it is not mandatory for a few known files.

A scenario should describe observable behavior, such as “an old load finishing after removal cannot reintroduce the route,” rather than merely naming a unit test to write. A capacity assumption must be identified as an assumption.

The opening can be a compact list or prose; no exact parser/schema is required. For example:

```markdown
# Recon: resumable export

- Repository: project identity from its documentation; affected code under src/export/.
- Task: resume interrupted exports without producing duplicate records.
- Scope: export entrypoint, checkpoint storage and callers; the remote sink was not inspected.
- Branch: the actual investigated branch.
- Baseline: the actual full commit SHA; clean, or the relevant uncommitted paths and captured evidence.
- Captured at: actual date/time with timezone.
- Next phase: design — READY_WITH_GAPS; local checkpoint semantics established, remote deduplication still to verify.
```

Replace example text with observed values. Use a documented repository identifier or a sanitized
remote identity where available; never include credential-bearing URLs. If the source has no Git
metadata, record the available identity/version and relevant file evidence instead of inventing a
branch or SHA. Existing reports missing these fields remain usable only after the consumer checks
their applicability in code.

Link relevant companion reports from the entrypoint with paths relative to that report. Lead the
user-facing answer with its conclusion; a development handoff also names the entry path relative
to the consumer repository, task/scope, source version and phase-specific readiness.
User-selected external output locations must be passed explicitly or
recorded in the project's existing artifact convention; a new session cannot discover arbitrary
external directories by guessing. Do not add a project instruction file merely to register a report.

## Expand only for a concrete need

For a formal audit, complex migration, cross-repository contract change or explicit handoff, add the sections and files needed by the reviewer:

- `report.md`: relevant flow, historical rationale, migration constraints and decisions; no fixed ten-section requirement.
- `contract-matrix.md`: useful when producer/consumer versions, owners or wire fields require separate tracking.
- `open-questions.md`: useful when unresolved decisions involve multiple owners or milestones.
- `baseline-evidence.json`: reproducible inventory if the collector was used.

A contract matrix can use:

| Contract | Inspected producer/consumer versions | Semantics and failure behavior | Evidence | Verification status | Impact on next step |
| --- | --- | --- | --- | --- | --- |

Use `verified_local_only` or `unverified_external` where appropriate; add an owner only when known. Do not invent ownership. For each important claim, cite the actual `commit:path:line` or captured working-tree evidence. A file list alone is not proof of a contract.

For a protocol/dependency change, make this comparison early; a small table in `report.md` is enough:

| Consumer revision and pinned dependency | Candidate dependency revision | Requested additions | Existing capabilities that must remain | Evidence and unresolved differences |
| --- | --- | --- | --- | --- |

Check relevant schema/types, routing/version mappings and semantics used by the consumer. Branch names, newer timestamps or the presence of the new symbol do not prove that existing capabilities remain. An unavailable candidate contract stays unverified; describe any required version combination as a target, not an already available release. Compilation can establish symbol compatibility when run, but does not replace semantic checks or prove deployment.

## Readiness and remaining questions

When evaluating readiness, name the phase: design, implementation, integration or release. Apply `READY`, `READY_WITH_GAPS` or `BLOCKED` to that phase only. List later phases as pending when they were not evaluated. For a factual investigation without a next-phase decision, describe what is established and uncertain instead of inventing a phase or blocking on an unchosen future design.

For each gap, explain the missing fact, the action it affects, why existing evidence cannot settle it, and when an answer is needed. Only call it blocking when the next action depends on the answer. Distinguish a potentially breaking unknown contract from a known contract whose live environment has not been tested.

## Keep the evidence timeline intact

Separate three kinds of statements: pre-change facts, accepted target decisions and implementation/validation results. Preserve the original baseline. Append dated discoveries or store follow-up evidence under a new filename; do not overwrite it with final-state descriptions.

After implementation, record verification in a separate section or file, including what actually ran, its result and material limits. Reading a test, passing a mock-based test and validating a production integration are different claims. Do not add passed-test labels retroactively to pre-change evidence.
