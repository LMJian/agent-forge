# Coordinate independent Git repositories

A group links independent tasks without merging their state or manipulating their branches.
Create one task per repository. At the committed integration baseline, write a local manifest
inside the coordinating repository, for example `.harness/runs/group-input.json`:

```json
{
  "schema_version": 1,
  "id": "location-integration",
  "goal": "Verify the protocol and location service together",
  "repositories": [
    {"id": "protocol", "path": "/absolute/alice_protocol", "task": "location-pb", "revision": "FULL_CURRENT_PROTOCOL_COMMIT_SHA"},
    {"id": "service", "path": "/absolute/event", "task": "location-server", "revision": "FULL_CURRENT_SERVICE_COMMIT_SHA", "depends_on": ["protocol"]}
  ],
  "contracts": [
    {"producer": "protocol", "consumer": "service", "path": "go.mod", "expected": "EXACT_ALICE_PROTOCOL_DEPENDENCY_DECLARATION"}
  ],
  "integration": {"repository": "service", "check": "location-e2e"}
}
```

Replace placeholders with actual paths, task IDs, full current commit SHAs and a sufficiently
specific dependency declaration. Configure and select `location-e2e` in the consumer task's
`stage_checks.integration` before linking; it must execute a real check of the required behavior.
The producer/consumer fields record the intended version relationship. A literal dependency
declaration match is evidence about the file, not proof of which artifact a deployment loaded.

Commands follow `python3 <plugin>/scripts/harness.py --repo <coordinator>`:

```text
link-repositories --manifest .harness/runs/group-input.json
repositories-status location-integration
record-group-check location-integration --repository service --run <actual-integration-run-id>
```

No `--task` is needed for group commands. Groups are saved under `.harness/runs/groups/`.
The link validates distinct Git identities, dependency order, current clean revisions and task
state. It does not run either task. Complete each repository's remaining stages normally and
run shared integration after linking; existing or reused check receipts cannot substitute for it.
Record the passing integration receipt with `record-group-check`.

Status reads both repositories live. `verified` requires all child tasks complete, current pins,
matching dependency declarations and intact shared integration evidence. `awaiting_integration`
means no shared check has been recorded; `in_progress` means a shared check exists but child work
remains; `stale` identifies changed revisions, dirty trees, altered evidence or dependency mismatch.
Changed pins require a new group ID and a new shared check; historical evidence is retained.

Shared integration assertions must verify the actual deployed versions when testing a lane or
remote environment, and separately establish report success, persistence/deduplication and
GetMemory readback when those are acceptance criteria. The core verifies receipt provenance;
it cannot turn a superficial check into behavioral coverage or proof of production deployment.
