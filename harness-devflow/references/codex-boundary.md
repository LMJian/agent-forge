# Codex native capabilities and Harness responsibilities

Reviewed against official documentation on 2026-10-30. This is an ownership comparison,
not a claim that project-specific policy is a defect in Codex. Available tools and actual
user authorization remain authoritative in each session.

| Area | Codex owns | Harness adds or retains |
| --- | --- | --- |
| Agent execution | Model/tool loop, command execution, progress and interruption | Selected check/adapter receipts bound to project code and configuration; no second agent loop |
| Conversation continuity | Chat persistence, resume and context compaction | Durable acceptance, decisions and evidence references; optional exports do not move chats |
| Planning | Reasoning, task planning and native progress display | Acceptance-to-task mapping and dependency validation; Codex profile materializes the accepted packet instead of authoring another plan |
| Permissions | Sandbox, command approval and security controls | Record project design/release decisions; a local actor/note is not identity verification or execution permission |
| Code review | Native local/PR review and findings | Check the current revision, acceptance coverage, required checks and unresolved blockers; reuse findings instead of launching another full review |
| Worktrees and agents | Managed worktrees, chat handoff and subagent lifecycle | Optional module dependency/integration bookkeeping; default current checkout; use available native tools when explicitly authorized |
| Scheduling | Native scheduled tasks and their lifecycle | Record the real monitoring handle and observed PR state; no plugin scheduler or invented background worker |
| Delivery | Available Git/PR/CI/deployment tools | Project-selected endpoints, reviewed revision checks and verified push/merge/deployment outcomes |

The useful additions are project contracts: a critical feasibility experiment when needed,
observable acceptance, evidence invalidation after relevant changes, explicit excluded tests,
and a concrete delivery endpoint. The native documents reviewed here do not specify this
plugin's acceptance schema or endpoint contract. That supports an additive workflow layer;
it does not establish a native correctness defect or prove a feature is absent everywhere.

## Keep the default path small

- Installing the plugin does not make it the owner of every Codex coding/review task. Enter
  through an explicit Harness request, an existing task, or the repository's configured default.
- Stage Skills apply to Harness stages. They should not attract ordinary Codex planning,
  implementation, reviews or scheduling requests.
- A builtin stage runs directly in the current Codex session. Prepare a professional handoff
  only for a selected non-builtin method; do not snapshot/re-invoke the same wrapper by default.
- Use Codex resume/compaction for continuity. Use `next` to recover project work, and `context`
  only for missing references. `ack-context` is optional, not mandatory read bookkeeping.
- Keep command bridges and custom host configuration for existing integrations that actually
  need them. Do not add them to a normal Codex project merely because the plugin supports them.
- Keep native security permissions separate from project sign-off. Neither approval supplies
  missing GUI, branch, message, scheduling or deployment authorization.
- If accepted behavior already exists, verify it and report `no_changes` with evidence. Do
  not require a cosmetic patch or empty commit to progress.

## Official sources

- [Codex harness and integration ownership](https://developers.openai.com/blog/codex-as-a-platform)
- [Native approvals and sandboxing](https://learn.chatgpt.com/docs/agent-approvals-security)
- [Native managed worktrees and chat handoff](https://learn.chatgpt.com/docs/environments/git-worktrees)
- [Native subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Native code review](https://learn.chatgpt.com/docs/code-review)
- [Native scheduled tasks](https://learn.chatgpt.com/docs/automations)
- [Scoped skills and progressive disclosure](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)
