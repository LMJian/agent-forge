---
name: brownfield-recon
description: Investigate existing code and contracts to establish the baseline needed for a specific change. Use for 存量逻辑调研、梳理旧逻辑、理解陌生仓库, or when a refactor, migration, or incident fix has unclear dependencies or compatibility constraints. Scale investigation to the task; a routine edit with an established baseline does not need a repository audit.
---

# Brownfield Recon

Find the existing behavior that matters to the user's change, the constraints it must respect, and the evidence needed to start work. Keep the investigation proportional to the decisions it supports.

Resolve scripts and references relative to this SKILL.md. The same method and report contract apply whether the skill runs standalone or inside a Harness capability invocation, so a report produced either way can be reused by the other. When invoked through Harness, read the capability request (`request.json`), write the report into its `output_directory` and return artifacts to the intake wrapper. For standalone investigation, use the location rules below.

## Scope and authority

- **Current behavior:** use code/runtime evidence from the relevant revision. A test that was read is not an executed test; local mocks do not verify a remote system.
- **Target behavior:** follow the user's latest instructions and accepted design. Record its source/version. A planned change from existing code is not a documentation defect; stale descriptions of current behavior are.
- Read applicable repository instructions. Reuse scope and authorization already established in the conversation. Ask only when an unresolved fact would materially change implementation or its safety.
- Investigation is read-only apart from the selected local recon artifacts. It does not authorize changes to business code, knowledge pages or remote systems. If the user already requested implementation, continue that authorized work after recon; do not seek approval again merely because this skill's investigation is finished.
- Exclude likely secret files before content search, including `.env*`, credentials, private keys and token dumps. Do not follow symlinks into unrelated or sensitive locations.

## Establish the change boundary

Identify the requested change, relevant entrypoints/modules, a few useful search terms, and the pre-change commit or working-tree state. Preserve existing user edits.

Choose the report location in the **consumer repository**, not the installed Skill directory. Honor a Harness request's `output_directory` (`.harness/runs/<task>/artifacts/capabilities/<id>/`) or a user-specified output location, then the project's existing artifact convention; otherwise use `.artifacts/brownfield-recon/<branch-key>/<run-id>/report.md`. Use a filesystem-safe branch key and a unique run ID, recording the actual branch in the report. For a non-Git source, use a task key and the available source identity. Reuse an explicitly selected report when reviewing it; a new investigation or follow-up must preserve earlier evidence.

Determine compatibility needs from available context: deployed consumers, persisted data, published interfaces and the user's explicit requirements. If the user confirms the code is unreleased and legacy compatibility is unnecessary, classify obsolete formats and adapters for replacement or removal. Do not invent a compatibility layer. Preserve required correctness and safety behavior; multi-version support in the target design is distinct from supporting an obsolete implementation.

Choose the amount of investigation without asking the user to select a mode:

- **Focused recon is the default:** inspect affected behavior, its direct callers/dependencies and relevant failure paths. Keep a short baseline and change table. A known, small scope can use direct reads without the inventory script.
- **Expand when evidence requires it:** unfamiliar architecture, migrations involving stored data, changes to public cross-repository contracts, or an explicit audit/handoff request can justify broader tracing and separate reports. Name the decision or uncertainty driving each expansion.

## Find and trace the necessary evidence

Start with the user's specified knowledge location or document, including custom directories such as `.artifacts`. In Harness, reuse the request's `input_reports`/`input_artifacts` and any local `knowledge-search` results supplied by the wrapper. Otherwise look for repository indexes, project documentation directories and earlier recon reports under `.artifacts/brownfield-recon/` or `.harness/runs/*/artifacts/`. Use the available repository or document tools to read relevant material, check freshness and corroborate important claims in code. A missing directory does not establish that no knowledge exists; missing knowledge is not a blocker or a reason to install another skill.

Trace each affected behavior through its caller/entrypoint, implementation, relevant schema/configuration, and result or failure path. Include persistence, retry, cancellation, routing or capacity where the change touches them. For unchanged dependencies, confirm the interface and reuse constraints; expand only if that reveals an impact. Mark irrelevant layers as not applicable rather than creating missing-contract questions.

Record what will be **retained, replaced or removed**, along with the reason and the behavior to verify. Tests that encode the old design may need replacement; tests of required correctness and safety remain useful.

Read [search-playbook.md](references/search-playbook.md) when deeper tracing, historical reconstruction or a remote contract requires it. Use Git history to answer a concrete question, not as a mandatory tour of every affected file. Generated code can identify a dependency but is not its sole contract owner.

For a broader inventory, run the bundled collector with an absolute output path; narrow content discovery with `--scope` where possible. Inside an active Harness invocation, use the wrapper's `collect-recon --scope ... --keyword ...` instead: it records the actual command and captures stdout in the run directory. The inventory is supporting evidence; it does not complete recon or determine readiness automatically.

```bash
python3 <absolute-skill-dir>/scripts/collect_evidence.py \
  --repo-root <repo-root> --scope <affected-path> \
  --keyword '<concept>' --base-ref <pre-change-commit> \
  --knowledge-root <user-specified-knowledge-directory> \
  --output <absolute-artifact-dir>/baseline-evidence.json
```

Omit optional arguments that do not apply. Check `warnings`, resolved `git.base_commit`, and `git.diff_semantics`. Branch diffs exclude uncommitted edits; inspect the separate working-tree fields. The collector identifies candidate files and samples, not verified behavioral conclusions. Do not rerun it just to fill a template.

## Stop when the next step is supported

Focused recon is sufficient when:

- the affected entrypoints, dependencies and disposition of old behavior are clear;
- critical changed interfaces have caller/schema evidence and relevant failure behavior inspected;
- required correctness, safety and real compatibility constraints are identified;
- concrete validation scenarios are known;
- remaining unknowns do not prevent safe work in the requested phase.

Then continue authorized implementation/design. Reopen only the affected trace if new evidence changes a decision. Do not finish unrelated repository areas for completeness.

Assess readiness **for a named phase**: design, implementation, integration or release. Do not infer release readiness from a local baseline.

- `READY`: evidence is sufficient for that phase; no blocking unknown remains.
- `READY_WITH_GAPS`: proceed within an explicit boundary, with remaining checks and when they are needed.
- `BLOCKED`: a specific unresolved fact makes the next action unsafe or prevents a correct implementation. State the fact, affected action, evidence already checked and required answer.

Unknown wire fields, data semantics or retry behavior can block implementation when the change relies on them. Lack of deployment access, real OAuth accounts or measured production capacity can instead remain integration/release checks when the local contracts are established. A mock or invented default must not stand in for an unknown external contract. Record tunable defaults as assumptions, not measured capacity.

## Preserve the baseline and hand off

Before editing code, capture a minimal baseline: source revision/state, important current behavior and a compact change table. Use a short `report.md` by default; do not create empty companion reports. See [report-contract.md](references/report-contract.md) for the compact format and when additional files help.

Make that report usable in a new session: include repository identity, task and affected paths, actual branch, source revision and relevant uncommitted state, capture time, and readiness for the named next phase. Link only companion artifacts that actually exist, using paths relative to the report. A collector JSON file supplies inventory, not this handoff or a readiness judgment.

Keep pre-change facts separate from target decisions and implementation results. During development, append new discoveries with their evidence; record final tests separately. Do not rewrite the original baseline into a description of the completed change.

Conclude with the report entry path relative to the consumer repository (or the explicit external location), its task/scope, baseline revision and phase-specific readiness, then the decision-relevant findings, planned disposition, gaps and validation cases. A downstream design Skill can discover this report under the artifact root (`.artifacts/` or `.harness/runs/<task>/artifacts/`) without relying on conversation memory. When handing off directly, pass the entry path; under Harness, also list it in the capability result's `artifacts`. Do not require another Skill installation just to produce the report. If implementation was requested, this is a progress update and input to the work, not a reason to stop the task. An applicable external workflow retains its own gates; recon neither approves nor advances them.
