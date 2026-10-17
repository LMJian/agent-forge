# Advanced/legacy host execution contract

The core owns project facts and completion rules. A host adapter executes a capability; the
builtin implementation remains available. Selecting a host name never grants capabilities,
permissions, background execution or approval.

## Selection

Project configuration uses this independent `host` object:

```json
{
  "name": "codex",
  "available": [],
  "command": {"provider": "auto"},
  "worktree": "auto"
}
```

The supported host is Codex. Legacy host names remain readable for existing tasks. Declare `worktree`,
`delegation` or `scheduling` in `available` only when the actual tool is callable in this session.
The skill reads host tools/instructions; the Python CLI cannot inspect an agent's tool list.
Use `host` or `doctor` to inspect the selected providers. The conservative default works with
any agent that can read files and execute Python/Git commands.

- Command `auto`: native only with a configured bridge, otherwise builtin.
- Worktree `auto`: native only when declared available, otherwise builtin.
- Explicit `native` without its prerequisite is a configuration error.
- Guided execution is serial. Autonomous execution allows native delegation when available;
  otherwise it is serial. Dependency waves and final checks apply in either case.
- Scheduling availability permits native observation when authorized. Without it, use bounded
  checks within the active session and resume later. There is no builtin background daemon.

Configuration is pinned to the task. Change it through `sync-config` after inspecting active
operations; this invalidates affected evidence. Never switch providers to work around a denied
permission, failed check or uncertain external result.

## Native command bridge

The bridge is trusted integration code, like a project delivery adapter. It may connect to a
host's supported execution API. It does not call another model merely to execute a test.
The plugin does not ship an assumed desktop RPC endpoint or require a private host API.

```json
{
  "name": "my-host",
  "available": [],
  "command": {
    "provider": "native",
    "bridge": {"argv": ["python3", ".harness/host-command.py"], "timeout_seconds": 360}
  },
  "worktree": "builtin"
}
```

Core writes a request file and passes its path in `HARNESS_HOST_REQUEST`:

```json
{
  "schema_version": 1,
  "request_id": "actual-run-id",
  "operation": "command",
  "argv": ["python3", "-m", "unittest"],
  "cwd": "/actual/module/checkout",
  "timeout_seconds": 300,
  "environment": {"HARNESS_TASK": "actual-task"}
}
```

Execute exactly the argument vector in the requested directory, forward the supplied environment
entries, wait for the actual result, and return one JSON object on stdout:

```json
{
  "schema_version": 1,
  "request_id": "same-actual-run-id",
  "outcome": "completed",
  "exit_code": 0,
  "timed_out": false,
  "stdout": "actual command output",
  "stderr": ""
}
```

Use `denied` for host refusal and `unknown` when the execution outcome cannot be established.
Never convert these outcomes to a successful response or invoke a second executor as fallback.
Responses are bounded to 1 MiB; preserve transport diagnostics on stderr. Native and builtin
execution both undergo the core's before/after code comparison and evidence validation.
A bridge is a trusted boundary, not proof against a malicious adapter.

## Native worktrees

`prepare-module MODULE` returns an `awaiting_host` request containing the exact `base_sha`.
Use the available, authorized host tool to create a worktree from that SHA. Then run:

```text
attach-worktree MODULE --path /actual/host/worktree
```

The core checks the Git common directory, exact HEAD, cleanliness, owning wave base and exclusive
module ownership. Detached HEAD is supported. Host paths may lie outside the owning checkout;
artifact paths still stay in the owning repository. Workflow commands always point `--repo` at
the owning checkout; module checks use the registered worktree automatically.

If a host only creates worktrees at another branch/default base, it does not satisfy this request.
Configure builtin execution before preparing the module rather than silently using a wrong base.
After attachment, the core verifies module changes and merges dependency waves. It never removes
host-managed worktrees. One component owns creation and cleanup; the core owns integration checks.

## Session handoff and scheduling

`handoff --output .harness/runs/TASK/artifacts/handoff.json` exports goal, stage, current code
identity, upstream artifact paths and the next action. Another host in the same checkout reads it
and calls `next`, which revalidates state and evidence. This is project handoff, not a copy of host
chat history and not automatic transport between different machines or checkouts.

A native scheduler is created only with actual user authorization; attach the returned handle
through `record-monitor`. Query adapters record actual PR/CI state. The handle alone does not
prove work is still running or that a PR merged. Poll only with a bounded active-session budget;
persist state and stop at that budget rather than inventing continued background work.

The host's permission system remains authoritative. Missing Python, filesystem access or command
execution prevents runtime enforcement; report the limitation rather than claiming equivalent guarantees.
