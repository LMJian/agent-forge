---
name: implement
description: "Execute module tasks and record verification for the implementation stage of an active Harness workflow."
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
   user changes and established error-handling conventions. Add validation at actual trust
   boundaries; add retries, fallbacks or abstractions only for a concrete contract, observed
   failure or required acceptance case. Keep unrelated hardening outside the implementation.
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
5. Inspect `verify-plan --module MODULE`, then run `verify --module MODULE` for the final code.
   The critical path runs first; unchanged deterministic checks may reuse their real receipts.
   For a local checkout target, implementation may remain uncommitted. For a remote target,
   commit the intended module changes before final verification to avoid invalidating the
   receipts immediately afterward. In worktree mode, commit module changes first so
   the core can integrate the exact verified commit. Do not include unrelated user work in a commit.
6. Write a result body containing `status`, `summary`, `completed_tasks`, `acceptance`, `artifacts`
   and actual `checks` IDs. Use `submit-module MODULE --result FILE`; do not write envelope fields.

If inspection proves the existing behavior already satisfies acceptance, keep code unchanged.
Submit `outcome: no_changes` with a concrete `reason` and the same required task coverage and
real checks. This is verified existing behavior, not a waiver or permission to omit a test.
Do not manufacture a code edit or commit merely to satisfy the workflow.

Checkout completion integrates the single module directly. In worktree mode, `merge-wave` runs
after all members are verified. Resolve actual conflicts using the intended behaviors and commit
the resolution before retrying. The next wave starts from the updated owning checkout.

## Execution and closure

Honor the execution provider reported by `next`. Guided mode and hosts without delegation run
serially. Autonomous mode may delegate independent modules only when the host exposes that
capability and the user/project authorizes it. Each worker receives repository/task/module IDs,
its working directory, task details and artifact references. Wait on actual returned worker handles;
a missing worker or a failure never counts as completion.

Use focused tests while diagnosing or changing behavior. Guided tasks need their required
checkpoints; autonomous work uses one final selected module batch, with earlier eligible
checks reused through `verify`. Module verification is not an extra semantic code review.
If the task plan materially changes, reopen plan. Preserve historical checkpoint artifacts and command logs.
When every module has integrated, submit an overall implementation result. Worktree cleanup is
separate; the plugin does not delete host worktrees or unmerged changes.

For `profile=codex`, apply the shared [acceptance and verification contract](../../references/codex-workflow.md).
Keep command, agent and human evidence distinct; reuse that contract instead of loading another copy.
