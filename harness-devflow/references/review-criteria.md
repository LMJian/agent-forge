# Evidence-driven review criteria

Apply criteria only when the changed behavior makes them relevant. A recommendation should
identify the trigger, the resulting failure and a concrete correction or verification gap.

| Area | Questions that affect delivery |
| --- | --- |
| Requirements | Does each acceptance criterion map to a design decision, implementation and observable test? |
| Contracts | Do callers and implementations agree on types, nullability, errors, ordering and compatibility? |
| State/data | Are transitions, ownership, consistency, idempotency, migration and recovery semantics closed? |
| Concurrency | Can retries, cancellation, partial failures or concurrent updates lose or duplicate work? |
| Security | Are changed trust boundaries, input validation, access checks and secret handling correct? |
| Resources | Are timeouts, cleanup, bounds and downstream load appropriate for the actual operation? |
| Operations | Can the shipped behavior be observed, rolled back and deployed in the intended order? |
| Tests | Do assertions observe the complete journey and final side effect in the required environment? Does the retained failure fail the old behavior and pass the fix? |

Use `blocker` for concrete correctness/security/data-loss or required-acceptance failures that
prevent proceeding; `warning` for a material follow-up that does not invalidate the deliverable;
`suggestion` for a useful optional improvement. Do not promote preferences into blockers.
Record uncertainty and inspect evidence before assigning severity. `resolved` means the
correction was made and verified, not that the finding was inconvenient.

Plans should be implementable and tie tasks to acceptance criteria. Review the complete relevant
diff, partitioned when necessary. Missing coverage should remain visible. Independent review
can improve confidence when available, but no specific model, agent count or vendor is required.

Check proof boundaries independently of test names/counts: a recovery/partial-output test can pass
while the required successful operation remains broken. Reference parity is not an independent
correctness oracle. Run critical paths before broad regression; reuse only identical declared
deterministic inputs, and keep live/device checks fresh. Missing permission is pending verification,
not product acceptance or an implicitly authorized scope reduction.
