# Profiles and delivery endpoints

Profiles select development depth. Endpoints select the requested deliverable. They are
independent; neither grants permission to push, create a PR, merge, schedule or deploy.

| Profile | Development stages | Default endpoint |
| --- | --- | --- |
| light | intake → plan → implement → review | local |
| standard | intake → design → design_audit → test_design → plan → implement → review | local |
| release | standard stages plus design_approval before interfaces/plan | deployed |

Use light for focused fixes or small reversible changes. Intake still records an approach
and verification method, and plan maps concrete tasks to acceptance. Standard suits features
with meaningful contracts or cross-module behavior. Release supplies formal design approval;
project/user requirements can select it on other profiles too. Do not make every change a
release workflow merely because it edits server code.

| Endpoint | Additional stages | Completion |
| --- | --- | --- |
| local | none | Verified local implementation |
| pr | push → pr | Actual PR/MR created; no merge wait |
| merged | push → pr → monitor | Observed merged PR/MR |
| deployed | push → pr → monitor → release → deploy | Release approved and deployment verified |

The deployed route currently uses the PR/merge path. Direct deployment without a PR is not
a separate built-in endpoint. Explicitly extending a completed task with `configure-flow
--target ... --reason ...` preserves earlier valid evidence and opens the additional work.
Changing scope does not undo remote effects or cancel an external scheduler.

## Configuration

The project-level `workflow` object and per-task CLI flags use the same options:

```json
{
  "profile": "standard",
  "assistance": "guided",
  "target": "local",
  "domain": "backend",
  "capabilities": {"recon": "auto", "design": "auto", "design_audit": "auto", "review": "builtin"},
  "isolation": "auto",
  "integration_position": "before_push",
  "knowledge_approval": false,
  "stages": {"interfaces": false, "knowledge": false}
}
```

| Option | Values and behavior |
| --- | --- |
| assistance | `guided` (default) returns one task with verified checkpoints; `autonomous` allows continuous work and ordered batch submission, with identical final checks |
| profile | `light`, `standard`, `release`; default standard |
| target | `local`, `pushed`, `pr`, `merged`, `deployed`; omitted/null uses the profile default |
| domain | `generic` (default), `backend`, `frontend`, `mixed`; backend selects bundled server design/audit methods |
| capabilities | Logical providers for `recon`, `design`, `design_audit`, `review`: `auto`, `builtin`, a bundled name or a project skill name; never an absolute path |
| isolation | `auto`: checkout for one module, worktrees for multiple; `checkout`: one module only; `worktree`: always isolated |
| integration_position | `before_push` by default; `after_push` for a pushed preview/environment, requiring a remote endpoint when integration is selected |
| knowledge_approval | false by default; true requires approval of notes, never of a `no_changes` outcome |
| stages | Boolean overrides for `design`, `design_audit`, `test_design`, `design_approval`, `interfaces`, `integration`, `knowledge` |

Interfaces and knowledge default off. Integration defaults on when the project assigns
nonempty `stage_checks.integration`. Design audit/approval require design. Development entry requires the four core stages. Explicit `start-review` entry excludes pre-review
development stages without marking them as executed. Review and selected delivery stages cannot
be disabled. `pushed` selects push without PR/monitor/release/deploy. A configured adapter alone
does not select an external stage. There is no arbitrary stage reordering; integration's
two supported positions retain the verified-code dependencies.

Example command suffixes (global `--repo` and `--task` precede them):

```text
start --goal 'Fix the parser boundary condition' --profile light --target local
start --goal 'Implement export' --profile standard --target pr --enable interfaces
start --goal 'Release export' --profile release --target deployed --enable knowledge
configure-flow --enable design --enable design_audit --enable design_approval --reason 'The change now includes a migration requiring review'
configure-flow --target pr --reason 'User requested a PR for the completed local change'
```

Task flags override project defaults; explicit stage overrides remain in force when changing
profile, so enable/disable them deliberately. `configure-flow` records the rationale and
invalidates the affected suffix. Use it for actual scope changes, not to hide failing checks.
Excluded stages remain excluded on reopen. If separate design/test design is removed after
intake, intake reopens to supply the required compact approach/verification.

Capability flags use `--capability SLOT=PROVIDER`; each supplied slot overrides only that slot.
`--domain backend` selects a design method without changing the profile or endpoint. Changing
a provider, or a domain affecting design/audit, invalidates that stage and its downstream work.
No capability enables a disabled stage. See the [handoff contract](../../../references/capabilities.md)
for bundle-relative resolution, preparation and result requirements.

## Execution assistance and host capabilities

Assistance is independent of task depth and delivery target. Guided mode is the default and
runs implementation tasks sequentially with ordered verified checkpoints. Autonomous mode
allows completing related tasks together. It permits parallel delegation only with actual host
capability and authorization; otherwise modules remain serial. An active implementation cannot
change assistance to weaken checkpoint requirements.

Configure the separate project `host` object using [the host contract](../../../references/hosts.md).
Native and builtin providers share quality rules. A host name never implies tool availability or
model capability. Missing native support selects builtin execution before the operation begins.
Permission denial, failed tests or uncertain effects never trigger automatic executor fallback.

`start-review --goal ... --base ... --acceptance ... --target pushed` selects an existing-change review entry with the light profile. Its entry cannot be changed after creation. See [focused tasks](../../../references/focused-tasks.md).
