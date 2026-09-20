---
name: server-tech-design
description: >-
  Draft, review, structure, and improve server-side technical designs (服务端技术方案 / TDD / RFC).
  Use for backend design decisions, design reviews, and making technical proposals clearer and
  more focused. Covers the core flow, contracts, relevant risks, monitoring, and rollout without
  imposing a fixed chapter inventory. Prefer this skill over generic document writing for backend designs.
---

# Server-Side Technical Design

Help a reviewer understand **what changes, how it works, why the important decisions are sound,
and how to verify and recover it**. Allocate detail according to the decisions the reader must make.

Resolve references relative to this SKILL.md. The same method applies standalone or inside a Harness
capability invocation. When a Harness request is supplied, follow its operation (draft or review),
input artifacts and local output directory; a shared design may cover several modules. Return
documents/findings to the stage wrapper; do not change workflow state or imply user approval.
Standalone design work does not require starting Harness.

## Operating principles

- **Establish the core solution before choosing headings.** A polished outline cannot repair an
  incomplete flow or an unresolved source of configuration, identity, or routing.
- **Review dimensions are not mandatory chapters.** Check the relevant engineering concerns internally;
  organize the document around the change. Preserve genuinely required sections in a user-provided template.
- **Keep consequential constraints visible.** Correctness, security, compatibility, and rollout constraints
  belong beside the decision or flow they constrain. Move exhaustive implementation detail to a reference
  or appendix when it would interrupt understanding.
- **Separate evidence from intent.** Distinguish existing behavior, proposed changes, estimates, and verified
  results. Do not turn an illustrative number, example configuration, or planned test into a confirmed fact.
- **Respect the requested operation.** A review or explanation does not automatically call for editing a
  document, changing code, publishing configuration, or starting a larger development workflow.

## Workflow

Adapt this workflow to the task. For a narrow edit, work from the existing design and check affected
connections; do not restart discovery or require another outline approval.

### 1. Establish the problem and the core solution

For a repository-backed draft or a change to the proposed behavior, first discover the relevant
existing baseline using [recon inputs](references/recon-inputs.md). Prefer explicitly supplied
reports (including a Harness request's `input_reports`/`input_artifacts`), then project-declared
artifact locations and the consumer repository's `.artifacts/` and `.harness/runs/*/artifacts/`,
including ignored/hidden files. This applies in a fresh session even when the user does not mention
`brownfield-recon`; do not rely on conversation memory. Resolve paths from the consumer repository,
not this Skill's installation directory.

Select reports by repository, task/scope, branch and source evidence, not modification time alone.
Read the selected entry report and its relevant linked artifacts; check changes since its baseline,
including uncommitted changes, before reusing consequential claims. Carry forward retain/replace/remove
decisions, validation scenarios and phase-specific gaps. Investigate only missing or changed facts.
If no applicable report exists, inspect the necessary code directly; neither recon nor Harness is a
mandatory prerequisite. A wording-only edit can reuse the existing document's established inputs.

Use the supplied material and relevant repository or document evidence to identify:
- The current problem, intended outcome, audience, and scope of change.
- A one-sentence proposed solution and the few decisions that determine its behavior.
- One concrete example that traverses the main flow, including the relevant changes and failures.

Trace where the inputs come from, who owns the state, how the target or version is selected, and what
happens when a step fails. For a configuration-driven service, discovery, loading, use, updates, and
withdrawal may be useful checkpoints; use only those relevant to the change.

Resolve consequential gaps before treating the solution as settled. Ask only for missing information
that cannot reasonably be inferred; continue independent work. Explain real alternatives for significant
trade-offs, without inventing options merely to populate a comparison table.

### 2. Organize around reader questions

Read [section-guide.md](references/section-guide.md) when choosing or restructuring sections. Select a
small set of questions the document must answer, then assign each section one primary responsibility.
Follow the causal flow: problem and scope, solution overview, how it works, then verification and rollout.
Rename, merge, or expand sections to fit the actual design.

For a new draft, [template.md](references/template.md) is an optional starting point, not a checklist to
fill. An inapplicable concern normally needs no public placeholder; explain exclusions only when a
required template or a plausible reviewer misunderstanding calls for it.

### 3. Draft at the right depth

Read [writing-style.md](references/writing-style.md) for drafting or readability work. Lead with the
conclusion and the main flow. Define easily confused concepts and their relationship before relying on
them. Prefer a focused diagram when it reduces explanation; place details where the reader needs them.

Use one primary explanation for a concept, contract, or failure rule. Annotated schema, field tables,
and examples have different purposes; avoid repeating the same field reference in all three.

Cite the baseline entry path, relevant source version and any newly verified differences near the
decisions they support or in a short source note. Preserve the original recon files; place the design
in a separate document at the requested destination. Keep inherited assumptions and pending checks
visible without copying the full recon report or treating its readiness as design approval.

### 4. Revise by replacing and consolidating

After a change, follow its dependencies through definitions, examples, diagrams, affected sections, and
references. Replace obsolete explanations, merge duplicates, and repair numbering and links. Do not
turn each conversation answer into a new paragraph or chapter. A local edit needs an affected-area check;
a changed core design needs a broader consistency pass.

Keep unresolved decisions separate from the explanation of the chosen design. Retain only open items
that affect implementation, compatibility, validation, or release; mark their consequence and next step.

### 5. Review comprehension and deliver

Use the applicable checks in [review-checklist.md](references/review-checklist.md). First ask whether a
reader can restate the solution and walk the example; then inspect completeness. Fix missing reasoning
and confusing structure, rather than adding a section solely to tick a box.

Match the user's destination and operation. Default to local Markdown in the supplied output
directory; for a new document with no specified destination, use the project's document or artifact
directory. For an existing document, preserve its location and relevant user annotations. External
publication is a separate action through the user's selected tool and destination. Use the
appropriate tools for the selected destination and their supported document and diagram formats.
Verify the rendered diagrams when applicable and the final affected content. In review mode, return
actionable findings and corrections instead of rewriting or publishing the document by default.

Report what changed and any material unresolved issue. Keep the internal checklist and discarded outline
out of the deliverable unless the user requests them.
