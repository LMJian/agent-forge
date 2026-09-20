# Recon Output

The output should support the next decision. Scale its form to the scope and audience; do not produce a fixed audit package for every edit.

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

The report itself is the entrypoint; a separate manifest, global index or collector JSON is not
required. A reader should be able to identify the right report from its opening context without
reading every inventory or remembering the producing conversation.

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

Link relevant companion reports from the entrypoint with paths relative to that report. Final
handoff names the entry path relative to the consumer repository, task/scope, source version and
phase-specific readiness. User-selected external output locations must be passed explicitly or
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

## Readiness and remaining questions

Name the evaluated phase: design, implementation, integration or release. Apply `READY`, `READY_WITH_GAPS` or `BLOCKED` to that phase only. List later phases as pending when they were not evaluated.

For each gap, explain the missing fact, the action it affects, why existing evidence cannot settle it, and when an answer is needed. Only call it blocking when the next action depends on the answer. Distinguish a potentially breaking unknown contract from a known contract whose live environment has not been tested.

## Keep the evidence timeline intact

Separate three kinds of statements: pre-change facts, accepted target decisions and implementation/validation results. Preserve the original baseline. Append dated discoveries or store follow-up evidence under a new filename; do not overwrite it with final-state descriptions.

After implementation, record verification in a separate section or file, including what actually ran, its result and material limits. Reading a test, passing a mock-based test and validating a production integration are different claims. Do not add passed-test labels retroactively to pre-change evidence.
