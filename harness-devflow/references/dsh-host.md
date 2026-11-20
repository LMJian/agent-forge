# DeepSeek Harness host mapping

The workflow skills are shared with the Codex packaging. This page maps the host-specific steps
they mention to DeepSeek Harness, so a DSH session follows the same workflow contracts without
Codex-only tooling. The Harness runtime itself (`scripts/harness.py`) is host-neutral; it needs
Python 3.10+ and Git in the target checkout.

## Invocation

- Codex calls `$harness-devflow:flow`. On DSH, the bundle registers every workflow skill by name
  (`flow`, `intake`, `plan`, `implement`, `design`, `design-audit`, `test-design`,
  `interfaces`, `integration-test`, `review`, `delivery`, `monitor`, `release`, `knowledge`,
  plus the bundled `brownfield-recon` and `server-tech-design`) and one entry skill,
  `harness-devflow`. Load the entry skill first when the user names the plugin; otherwise load
  `flow` for a new or resumed task.
- Each skill's base directory is `<plugin-root>/skills/<name>`, so the plugin root is two levels
  up. Run `python3 <plugin-root>/scripts/harness.py --repo <target-checkout> <command>`; do not
  copy the runtime into the target repository.
- `profile=codex` in the runtime and in the skill text names the Harness workflow profile. It is
  not a requirement to run Codex.

## Tool equivalents

| Contract wording | DeepSeek Harness tool |
| --- | --- |
| Shell/CLI execution | `bash` (or a persistent terminal when configured) |
| Read a file | `read`; previews also use `read` with offset and limit |
| Create or replace a file | `write` |
| Targeted edit | `edit` |
| Search paths / contents | `glob` and `grep` |
| Delegation | `subagent`, `subagent_fork`; `workflow` only for explicitly requested large fan-out |
| Task list | `todo_write` |
| Deliverable handoff | `present` |
| Images or screenshots | `read_image` |
| Reminders | `schedule_create` and related tools, only when explicitly requested |

## Context, approvals and boundaries

- Use the host's own resume, compaction and conversation continuity. `export` still writes a
  progress report; it does not move the conversation.
- DSH approval prompts and permission modes replace Codex approvals. Treat an approval prompt as
  the user decision it is; do not re-request escalation the user has not granted, and do not
  treat tool availability as authorization.
- Branch consent is unchanged: creating or switching a development branch, naming a detached
  checkout, or using another worktree requires the user's explicit request or agreement. DSH has
  no built-in worktree manager, so use Git directly and only within that consent.
- Computer Use, publishing, deployment and other external writes keep their separate
  authorization; the workflow never grants them implicitly.
- Evidence rules are unchanged: unit tests and builds do not replace product-level acceptance, and
  file replays do not replace runtime behavior.
