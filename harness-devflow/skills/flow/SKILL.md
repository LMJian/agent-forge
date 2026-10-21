---
name: flow
description: "Run or resume Harness development, review existing changes, coordinate repository tasks, or deliver through an explicit pushed/PR/merged/deployed endpoint."
---

# Development workflow

Use for a requested development workflow or an existing Harness task. A question about a
workflow does not start one. Resolve the plugin root from this file's location; the consumer
repository is the user's target checkout. Read [the runtime contract](references/runtime.md).
Use [workflow ownership](../../references/routing.md) to select one orchestrator. Never start
a second workflow over an active task just because a similarly named skill is available.

## Start or continue

1. Read applicable project instructions. Establish the actual goal, acceptance scope, repository
   and task ID. Keep the selected model and host permissions. Default to development on the
   current branch (`isolation=checkout`). Creating/switching a development branch, naming a
   detached checkout, or using a separate worktree requires the user's explicit request or consent.
   Dirty files, a branch prefix, autonomy or a workflow profile are not authorization. Do not use
   raw Git or host tools to bypass this rule; see [branch consent](../../references/branch-consent.md).
2. Default new projects to `profile=codex`, `assistance=autonomous`, `target=local`.
   Follow [the Codex contract](../../references/codex-workflow.md): one decision packet, continuous
   implementation, product verification. Read it before intake. Existing task choices and explicit
   user requirements persist; `standard`/`release` remain for separately requested design stages.
3. Run the smallest representative feasibility probe before committing to a risky architecture.
   Do not defer proof of the primary product outcome until human acceptance. Prefer one module.
4. This plugin targets Codex. Prefer builtin CLI/API execution and authorized Codex tools. Do not
   inspect generic host adapters or model vendors unless an existing project actually uses them.
   GUI, delegation, external delivery and scheduling still require their applicable authorization.
5. If needed, run `init` and configure real project checks and selected delivery adapters.
   Inspect project scripts rather than inventing a passing check. Run `doctor` with the intended
   profile and endpoint. A Git repository with an initial commit is required. Detached HEAD
   and existing uncommitted changes are supported; preserve user changes.
6. Start with `start --goal ... --profile ... --assistance ... --target ... --domain ...`.
   For an existing diff, use `start-review --goal ... --base <verified-baseline> --acceptance ...`
   instead of inventing intake/plan/implementation history. Use `--target pushed` when the
   user requests only a push; it does not create a PR. See [focused tasks](../../references/focused-tasks.md).
   For a started task, run `next`. Read its action, inputs and returned Skill path. That command
   starts a pending stage and produces a concrete work packet. `status` is read-only.
   Read only needed `inputs`; after reading, optionally `ack-context <content_id>` so unchanged
   material is identifiable on the next packet. Use `context --all` only for missing historical context.
7. Execute the returned action and submit the actual result. Repeat `next` while authorized
   work remains. Finish at the selected endpoint. An internal routing message is not delivery. In Codex mode, `next` computes the plan from
   the accepted intake packet and stops at any selected approval; do not author a duplicate plan.

## Action handling

- `execute_skill`: read the returned Skill and cited upstream artifacts. Do the work and use
  `submit --result <body.json>`. The runtime creates the envelope and links actual check receipts.
- `prepare_module`: run its command. Builtin execution returns the checkout; native execution
  may return a worktree request. Follow that request and `attach-worktree` after creation.
- `implement_task`: default autonomous execution completes related tasks together. If explicitly
  guided, complete the next planned task, run a real check and
  record `checkpoint`. In autonomous mode complete related tasks together, then verify the module.
- `submit_module` / `merge_wave`: follow [implementation](../implement/SKILL.md).
- `inspect_execution`: inspect process state, logs and external effects. Reconcile an uncertain
  operation before retrying. Do not switch providers to evade a refusal or duplicate a side effect.
- `repair_evidence`: reopen the identified affected stage, or synchronize an intentional config
  change. Preserve prior artifacts. Never edit state fields to declare them fresh.
- `approval`: present the existing concrete artifact and obtain the required actual decision,
  respecting authorization already supplied. Record it with `approve`.
- `diagnose`: inspect failures and retry budget; revise the plan or reopen with a specific reason.
- `finished`: report delivered artifacts, verification and material remaining limitations.

The returned Skill may be loaded by the host or read as Markdown directly. The plugin bundles
`brownfield-recon` and `server-tech-design`; resolve those through package-relative paths and
[professional handoff](../../references/capabilities.md). Do not require personal skill paths.

## Verification efficiency

Use `verify-plan` to inspect order, cost and safe reuse, then `verify` for the selected check batch.
Run the smallest real critical-path/regression check before expensive broad checks. Use `test-progress` before asking for any human
operation or reporting completion. Keep automation, authorized agent actions and unavoidable human
work distinct. Report remaining cases and human batches, not just how many unit tests passed.
See the [Codex contract](../../references/codex-workflow.md) for evidence reuse and failure recovery.

## Approval and recovery

For selected design approval or release, assemble a concrete packet and `submit` it. Runtime
returns `waiting_human`; it does not invent an approval. `approve STAGE --actor ... --note ...`
records an applicable real decision. Routine guided checkpoints never request human approval.

`reopen` preserves history and invalidates downstream evidence without reverting code or remote
actions. `sync-config` accepts an intentional project change and invalidates affected work.
`configure-flow` changes actual scope/endpoint, not a failed check's outcome. Choose assistance
before planning; an active implementation cannot weaken its checkpoint requirements.

`handoff --output <new-file>` records the project goal, next action and artifact references for
another host in the same checkout. `export` produces a human-readable progress report. `abort`
stops the task; separately cancel any real scheduler when authorized. Neither action deletes worktrees.

For multiple Git repositories, keep one task per repository. At the committed integration
baseline, use `link-repositories --manifest FILE`, run the selected shared integration check,
and `record-group-check`. Inspect `repositories-status` before declaring the whole change
verified. A version-string match alone is not behavioral integration evidence; see
[repository groups](../../references/repository-groups.md).

Only interfaces, integration and knowledge may be skipped with an actual applicability reason.
Missing credentials, failed checks or unavailable required infrastructure are blockers. Native
capabilities and builtin fallbacks obey the same completion rules.
