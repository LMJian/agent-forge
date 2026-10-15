# Existing changes and deterministic check reuse

All commands below follow `python3 <plugin>/scripts/harness.py --repo <checkout> --task <id>`.

## Review an existing diff

Configure real project review checks with `init` and `.harness/project.json`. Determine the
intended baseline and acceptance from the user's request and actual code, then:

```text
start-review --goal 'Review the location upload change' --base origin/master --acceptance 'Payloads preserve the agreed 16 fields' --target pushed
next
run-check unit
submit --result <review-result.json>
```

Repeat `--acceptance` for additional criteria. This explicit entry starts at review; earlier
development stages are excluded, not reported as executed. `review_context` contains acceptance,
the resolved baseline SHA and diff scope. The reviewer still reads the complete relevant diff,
runs selected checks and records material findings. A question about a diff does not authorize
push, PR creation or fixes outside the requested scope. `local` is the default endpoint.

`pushed` selects push without PR/merge/deploy. Selected integration and knowledge stages still
apply. The bundled Git adapter checks the remote branch SHA after push and requires an explicit
remote. A failed readback is an unverified outcome; reconcile remote state before retrying.

## Opt-in deterministic checks

Checks always execute unless `reuse-check` is explicitly requested. To make an offline,
deterministic check eligible, add `reuse` to its existing check specification:

```json
{
  "argv": ["python3", "-m", "unittest", "discover", "-s", "tests"],
  "reuse": {
    "context_files": [".toolchain-fingerprint"],
    "max_age_seconds": 1800,
    "assumptions": "Offline tests; all dependencies are represented by tracked files and the toolchain fingerprint; independent of Git history and HARNESS variables"
  }
}
```

Generate the context file from the actual environment (runtime versions, installed dependency
hashes, relevant external configuration) and refresh it before requesting reuse. The core hashes
its contents; it cannot infer whether a manually maintained manifest reflects reality. Use an
empty list only when no extra dependency inputs exist. Do not enable reuse for network/live
service checks, nondeterministic tests, tests depending on timestamps or Git history, or checks
whose ignored/external dependencies cannot be accurately fingerprinted.

The runtime compares current working bytes, filenames, executable bits, symlink targets,
command/configuration, checkout path, environment hash, executable binary and declared context
files. Environment values are hashed, never stored. Native-host execution and submodules are
unsupported for reuse. Ignored files are included only when explicitly declared as context files.

After committing already tested bytes:

```text
reopen review --reason 'Check the final commit; deterministic test inputs are unchanged'
next
reuse-check unit --from <original-executed-review-run-id>
submit --result <new-review-result.json>
```

If review is still running, omit `reopen`. Reuse is limited to the same task, checkout and review
check. It does not reuse implementation/integration checks or external adapters. An intervening
failed check, changed inputs, modified evidence or expired original result rejects reuse. A reused
receipt points at original execution logs and retains the original timestamps; it does not extend
their lifetime. Inputs and expiry are rechecked at submission and before delivery. The final
review always binds to current HEAD, and push still requires clean, reviewed code.

## Read only relevant context

`next` and professional handoffs select stage dependencies. Implementation packets narrow
module design artifacts to the active module. References have a `content_id` and `read_status`
of `unread`, `unchanged` or `changed`. Only after actually reading a reference, use
`ack-context <content_id>`; this records a read, never an approval or a verification result.
`context --all` is a read-only escape hatch for complete historical references. Stale artifacts
still block progress even if their read status is `unchanged`.
