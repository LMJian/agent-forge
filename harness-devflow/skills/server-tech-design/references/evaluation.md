# Behavioral evaluation for Skill maintenance

Load this only when changing or evaluating the Skill. The reusable inputs are in
[evals/cases.json](../evals/cases.json). They are synthetic, local-only scenarios, not evidence about a
real service. They test decisions and preserved meaning, not exact generated wording or heading names.

## Run a case

1. Materialize that case's `files` inside its own temporary directory. Paths are relative to that directory.
   Do not mix fixtures with a real repository or treat example deployment statements as live evidence.
2. Give the executor the Skill path, the case's `request` and those raw files. Do not pass the grading
   criteria, an expected answer, a suspected defect or a prior evaluation result. Respect the case's
   permitted operations. No case authorizes remote writes, GUI actions or dependency installation.
3. Keep the actual output and tool/action record. Record the Skill content hash, executor, case ID and
   observed validation limits. A same-agent walkthrough must be labeled as such; it is not an independent run.
4. Grade the actual result against `criteria`. For editing cases, compare protected sections and input
   hashes. For reviews, inspect the causal argument and evidence anchors. For language checks, verify that
   the actor, conditions, numbers, negation and result retain their meaning after simplification.
5. Record each criterion as pass/fail/not_checked with an output location or observed action. Missing
   records are not proof that an action was avoided. Repeat only affected cases after a correction.

Independent forward testing may be used when available and authorized by the current session. Otherwise
use a clearly labeled local walkthrough and leave independent behavior unverified. Do not invoke another
model or install an evaluation runner solely to make the report look complete.

## What each validation establishes

| Validation | Establishes | Does not establish |
|---|---|---|
| Skill frontmatter and reference checks | The package can be discovered and its resources exist | The generated prose is clear or the proposed system is correct |
| Standalone/bundled content comparison | Both entrypoints receive identical maintained instructions | A pinned snapshot in an existing run has been upgraded |
| Harness capability tests | Routing, snapshots and findings handoff preserve the runtime contract | An agent performed a substantive design review |
| Actual scenario execution and semantic grading | The observed output/actions meet that scenario's criteria | Universal STE compliance, production behavior or success on untested cases |

The cases cover Chinese simplification, narrow edits, review-only operation, code/design conflict,
missing diagram tools and a clean review. Preserve the task's meaning and scope; do not reward longer
documents, invented blockers, arbitrary word counts or merely mentioning the name ASD-STE100.

Keep evaluation results outside the distributed Skill. A maintenance summary should distinguish
automated checks, manual walkthroughs, independent agent runs and live-service checks.
