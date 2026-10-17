---
name: implement
description: "Implement planned module tasks with guided checkpoints or autonomous execution, verify actual behavior and integrate dependency waves."
---

# Module implementation

Read [the runtime contract](../flow/references/runtime.md). Run `next` and read the current task,
acceptance, check commands and upstream artifacts. Use the returned working directory; workflow
commands always point to the owning repository and task ID.

## Prepare and implement

1. Run `prepare-module MODULE`. For builtin execution, edit the returned `worktree`. For an
   `awaiting_host` request, use the authorized host tool at the exact requested base SHA and
   `attach-worktree MODULE --path ...`. The core checks repository identity, base and ownership.
2. Follow the recorded task IDs, expected behavior and verification method. Preserve existing
   user changes. Use relevant project methods and environment tools when available.
3. In **guided** mode, implement the next task, run a configured check with `--module MODULE`,
   save the observed behavior/results in an artifact, and run:

   ```text
   checkpoint --module MODULE --step TASK_ID --summary 'Observed implemented behavior' --check RECEIPT_ID --artifact PATH
   ```

   Every planned task needs its own ordered checkpoint. Read `next` after each checkpoint.
   A real failed, unrelated or stale check cannot satisfy it. These are programmatic checks,
   not additional human approval gates.
4. In **autonomous** mode, related tasks may be implemented together. Checkpoints remain
   available; final task coverage and module checks are still required.
5. Run all configured review checks for the final module code. In checkout mode, uncommitted
   implementation can be verified locally. In worktree mode, commit module changes first so
   the core can integrate the exact verified commit. Do not include unrelated user work in a commit.
6. Write a result body containing `status`, `summary`, `completed_tasks`, `acceptance`, `artifacts`
   and actual `checks` IDs. Use `submit-module MODULE --result FILE`; do not write envelope fields.

Checkout completion integrates the single module directly. In worktree mode, `merge-wave` runs
after all members are verified. Resolve actual conflicts using the intended behaviors and commit
the resolution before retrying. The next wave starts from the updated owning checkout.

## Execution and closure

Honor the execution provider reported by `next`. Guided mode and hosts without delegation run
serially. Autonomous mode may delegate independent modules only when the host exposes that
capability and the user/project authorizes it. Each worker receives repository/task/module IDs,
its working directory, task details and artifact references. Wait on actual returned worker handles;
a missing worker or a failure never counts as completion.

Use focused tests for each task and the full selected module checks at completion. If the task
plan materially changes, reopen plan. Preserve historical checkpoint artifacts and command logs.
When every module has integrated, submit an overall implementation result. Worktree cleanup is
separate; the plugin does not delete host worktrees or unmerged changes.

## Codex verification contract

Follow [the Codex contract](../../references/codex-workflow.md). Prefer command/API/replay checks;
use authorized GUI actions when appropriate. Reserve human cases for stated limitations and group
them into a batch. `verify` runs selected checks and records command cases; `test-progress` reports
remaining cases. Product-level outcome evidence is required in Codex mode, independently of passing
unit/build checks. A user waiver remains an exclusion. Do not repeat manual work after the same
failure: preserve inputs, diagnose and verify the changed product path before requesting another run.
