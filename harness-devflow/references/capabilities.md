# Professional skill handoff

Harness keeps the workflow stages, report schemas and gates. Professional skills supply
investigation, design or review methods. They never approve a workflow or synthesize command
receipts. The CLI selects/snapshots a skill and records results; the agent performs its work.

## Bundled providers

The distribution includes:

- [brownfield-recon](../skills/brownfield-recon/SKILL.md), its collector and two references;
- [server-tech-design](../skills/server-tech-design/SKILL.md), with its writing, structure,
  template and review references.

Resources resolve from the plugin's own location. Both skills write to the local output directory
supplied in the capability request. The bundled copies are byte-identical to the standalone skills
distributed beside this plugin and follow the same report contract, so a standalone recon report
under `.artifacts/` can be supplied as a Harness input report, and a Harness recon report under
`.harness/runs/<task>/artifacts/` can be reused by a later standalone design session. Resource
provenance and the drift check are recorded in [bundled-skill-origins.json](bundled-skill-origins.json). The collector excludes Harness-generated
runtime data from its evidence inventory.

| Slot | Harness stage | Auto choice |
| --- | --- | --- |
| recon | intake | bundled brownfield-recon, when investigation is needed |
| design | design | bundled server-tech-design for backend; builtin for other domains |
| design_audit | design_audit | bundled server-tech-design in review mode for backend; otherwise builtin |
| review | review | builtin; a project provider may supply domain review |

Configure `workflow.domain` as `generic` (default), `backend`, `frontend` or `mixed` and
`workflow.capabilities` as slot-to-provider names. CLI overrides use:

```text
start --goal 'Add export' --domain backend --profile standard --target local
configure-flow --capability design=builtin --reason 'This design concerns a generic tool'
configure-flow --capability recon=brownfield-recon --reason 'Investigate the existing compatibility contract'
configure-flow --capability review=project-review --reason 'Use the project review method'
```

Provider names are `auto`, `builtin`, a bundled skill name, or a project skill directory name.
Project providers live in `.harness/skills/<name>/SKILL.md`, with relative references/scripts.
Bundle names always resolve to the plugin copy; a project file cannot silently shadow them.
Paths are resolved at runtime. No absolute source path belongs in project configuration.
Auto may fall back to builtin if a provider is unavailable, with a recorded reason. Explicit
missing or incompatible providers fail clearly; do not silently substitute another method.
Stage-disabled capabilities do not add stages. Mixed tasks retain generic design by default;
apply backend guidance only to the relevant modules when explicitly selected.

## Prepare, perform, normalize

After `next` starts the relevant stage:

```text
use-skill recon --reason 'The persisted format and old callers are unclear'
use-skill design --reason 'Design the new backend behavior'
```

The result identifies the provider, original source, source digest, pinned `skill_path`,
`request` JSON and `output_directory`. Preparation is idempotent for the current stage epoch.
It snapshots the selected skill and its references/scripts/assets inside the run. Later source
updates or moving the installed plugin do not silently change that invocation. Source packages
are bounded and cannot contain symlinked resources. A reopened stage selects a fresh snapshot.

Read the request, then the pinned professional SKILL.md and only relevant references. The
request supplies goal, domain, operation, input reports, code revision and local output directory.
For a builtin choice, continue the current stage wrapper's method; do not recursively invoke
it or submit an extra capability report. Its completion is recorded by the main stage report.

Submit a professional result body; the CLI supplies the invocation envelope:

```json
{
  "status": "pass",
  "summary": "Describe the supported baseline and any phase-specific gaps",
  "artifacts": [".harness/runs/task/artifacts/capabilities/id/report.md"],
  "details": {"phase": "design", "readiness": "READY_WITH_GAPS"},
  "tool_runs": []
}
```

Submit with `record-skill <slot> --result <file>`. Recon readiness names the request's
next phase (design or implementation), not a later release claim. `BLOCKED` pairs with
`status: blocked`, prevents advancing the Harness stage, and can be resolved with a new result
file that preserves the original evidence. Inventory is not readiness; inspect code/contracts.

Design/audit/code-review results use the same envelope without recon details. Audit and code
review include explicit `findings` with `severity: blocker | warning | suggestion`, `message`,
and `resolved: true` only for resolved blockers. A pass cannot contain unresolved blockers.
The main audit/review report must incorporate those findings. Code changes after a professional
code review invalidate it. Complete professional review after fixes and final checks; rerunning
the affected review uses `reopen review` and a fresh capability invocation.

Then complete the normal Harness stage:

- Intake keeps acceptance IDs and module dependencies; link the baseline rather than repeating it.
- Design keeps `details.designs`; multiple modules may map to one shared professional document.
- Audit keeps the cross-module/acceptance checks and normalized findings.
- Code review still needs actual configured command receipts and its final findings.

An explicit provider must have completed evidence before its stage can pass. Auto recon can be
omitted for an established baseline; other stage wrappers prepare their method when operating
the workflow. All selected capability reports, source snapshots and cited outputs enter the
stage's content-hashed evidence. These records show what the agent reported using; they are
not proof of semantic review quality or a separate authenticated approval.

## Optional recon collector

With a prepared bundled recon invocation:

```text
collect-recon --scope src --scope tests --keyword export
```

This executes the pinned bundled collector using argv, captures `--output -` into a real
command log and returns its receipt ID/stdout path. Include that ID in `tool_runs` and the
relevant inventory in the baseline. Timeouts, malformed JSON, code changes and nonzero exit
codes fail normally. Reuse the existing runner's interruption/retry handling. No generator
or remote API is called. Narrow source scope when useful; `.harness`, `.artifacts`, sensitive
files and symlinks are excluded by the collector. Direct standalone output also supports
`.harness/runs/<task>/artifacts/` without overwriting existing evidence.

## Reuse and recovery

Use the baseline as the reference for pre-change facts; append later discoveries separately.
Test design takes scenarios from recon/design and fills coverage gaps, rather than producing
duplicate suites. Planning, code review, integration and knowledge reuse those artifacts.
Fresh code inspection remains necessary when a decision or current change depends on it.

`configure-flow` changing a provider or relevant domain invalidates the affected stage and its
downstream work while preserving previous invocation history. Current state is validated without format conversion.
