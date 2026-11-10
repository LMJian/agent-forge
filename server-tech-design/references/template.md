# Template — Start from the Core Questions

Use this optional skeleton for a new design. Rename, combine, or remove sections to fit the change;
expand only where the reviewer needs an independent explanation. An explicit user or project template
takes precedence. Prompts below guide drafting and should not remain in the delivered document.

Include owner, review status, and source links when known or required. Keep dates, sign-offs, test results,
and deployment status factual. Add an unresolved item only when its answer affects the design or readiness.

---

# 1. Problem

_Explain the current behavior, the problem, and the intended outcome.
Use a meaningful measure of success where available; identify a proposed target as such._

# 2. Core design

_State the solution in one sentence. Use the views below when they answer separate questions.
Explain significant trade-offs beside the relevant decision._

## Module dependencies

_Use a module dependency diagram to show roles, important dependencies, state ownership, and change status._

## Core interaction

_Use a sequence diagram to follow one scenario through the main calls, state changes, and observable result._

# 3. Change scope

_The Spec gives the change, reason, and delivery category per affected component. The Plan gives the
dependency order, owner, and completion criterion for each phase. Combine them in a compact form when useful._

# 4. How it works

_Replace these prompts with sections named after the actual design questions. Follow one representative
example from input to result. Trace relevant preparation, state changes, updates, failures, and removal
without requiring every design to have all of these stages._

_Introduce the contract or configuration structure before examples. Identify sources of truth and
ownership; explain confusing concepts together. Keep the exact contract accessible through an annotated
schema or field reference, and label illustrative or unvalidated payloads._

_Place correctness, security, compatibility, and resource constraints alongside the behavior they govern.
Explain what callers observe on failure and what continues working. Link detailed mechanics only when
needed; do not repeat each constraint in another chapter._

# 5. Verification and rollout

_Expand the verification and rollout decisions that need detail beyond the Plan.
Distinguish planned checks from executed results and link actual evidence when available.
Address material performance or capacity assumptions here or beside the affected decision._

_Identify the essential monitoring; reuse existing metrics when adequate. Keep this table compact and
adapt its columns to the change._

| Object | Metric or measurement | Meaning and dimensions | Alert condition |
|---|---|---|---|

_When release work applies, describe the order, observation period or criterion, abort conditions,
and rollback mechanism. Show the effect on existing requests, versions, or data when relevant.
Use required project controls with their source; do not invent an FG name or approval status._

## Open decisions — only if material

_What remains undecided or unverified, what it affects, and how it will be resolved. Keep this separate
from the chosen design; omit the section when nothing relevant is open._

# Appendix — only if useful

_Link implementation details, extended contract references, verification inventories, policy sources,
or review records needed by a subset of readers. Omit an appendix that merely repeats the main text._
