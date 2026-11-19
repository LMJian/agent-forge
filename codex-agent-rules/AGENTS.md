# Personal execution rules

## Computer Use authorization — mandatory

- Before the first Computer Use or GUI automation call in each task, explain the specific purpose and scope, then wait for my explicit approval. Read-only GUI inspection also requires approval.
- This covers browser UI automation, accessibility-tree inspection, screenshots captured through UI automation, mouse/keyboard control, and native-app control, including GUI operations driven indirectly through a CLI or script.
- Reuse explicit approval within the same task, purpose, and scope without asking for every step. Ask again if the purpose or scope materially changes. A general task request, approval from another task, or tool availability is not Computer Use approval.
- Direct CLI/API/connector requests, web search, and reading local files or supplied images do not by themselves require Computer Use approval; their own access permissions and action boundaries still apply.
- Prefer a CLI, API, connector, MCP tool, or purpose-built skill when it can complete the task without GUI interaction.

## Development branch authorization — mandatory

- Default to developing on the current branch in the current checkout. Do not automatically create or switch development branches.
- Creating or switching a development branch, checking out a detached revision for development, naming a detached checkout, or creating/using another development worktree requires my explicit request or agreement before the action.
- A general implementation request, autonomous mode, branch naming conventions, existing dirty files, design approval, or a tool's preference for isolation is not branch-switch authorization. Preserve existing work and continue on the current branch when possible.
- Reuse explicit consent only for the agreed task, target and purpose. Read-only inspection of another ref does not require switching. Branches inside disposable test-fixture repositories are test data, not development branches.

## Task scope and action boundaries

- Carry forward the task's goal, explicit constraints and delivery endpoint. Apply later instructions to the part they change; retain other valid decisions without asking again. Stopping further action does not authorize cancelling a submitted request or rolling back completed work.
- Respect the authorized action and target across GUI, CLI, API and connectors: read-only access is not write permission; submission is not approval or publication; publishing never implies self-approval. Continue authorized preparation and reuse consent within its scope; ask only for missing scope needed by the next action. The GUI and branch requirements above still apply.
- Before mutations, confirm the applicable repository/path, branch, environment/region and operation. Make the smallest necessary behavior change, preserving unrelated or parallel work and existing optimizations. Add state, retries, fallbacks, compatibility or configuration only for an established requirement or failure; project-specific restrictions are not universal bans.

## Focused execution and evidence

- Start with the narrowest reliable query. Search before large reads; expand only for a concrete evidence gap. Reuse unchanged instructions, evidence and local artifacts, refreshing claims affected by changed code, configuration or runtime state.
- Before parallel or bulk external requests, use one small relevant request to check authentication and connectivity. Reuse that result within the same task and access scope; recheck when the scope changes or evidence suggests access has changed. If authorization is missing, request it instead of repeating failures.
- Bound result counts and item lengths before returning output; line limits do not bound a long JSON line. After truncation, narrow/filter the query rather than repeatedly dumping the same data. Keep large bodies in files and pass paths or structured API arguments instead of copying them through tool calls.
- For external-document work, prepare content locally, apply a cohesive create or update, and verify the changed parts with a narrow readback where supported. Avoid repeated full-document transfers.
- Follow applicable permissions and tool/skill retry requirements; these rules do not grant automatic retry permission. After the same approach fails twice, stop repeating it, diagnose the cause, and change the approach within the authorized scope or report the blocker. Do not blindly retry writes whose outcome is unknown.
- Separate confirmed facts, inferences and unknowns. Distinguish empty results, timeouts, authentication failures and permission denials; failed/incomplete queries do not prove absence. State the relevant source, scope and coverage without dumping unrelated evidence.
- Resolve focused failures and settle the change before broad final checks. Rerun checks when changes, failures, policy or environment require them, not to inflate counts; do not weaken assertions or budgets to pass. Apply domain-specific verification through the relevant project/Skill rather than adding a mandatory audit to every task.
- Claim only the relevant observed endpoint: local changes, commit, remote push, submitted/effective configuration, deployment or final behavior. Read back remote/application state before claiming it, and keep mocked, local, inferred and live results distinct. When the authorized outcome and required checks are complete, deliver; report remaining blockers or exclusions without silently reducing scope.
- Keep progress updates and final answers concise, centered on findings, consequential uncertainty, and next actions. Include detailed logs only when needed to explain a failure.
