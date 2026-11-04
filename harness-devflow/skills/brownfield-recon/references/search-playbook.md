# Focused Search and Evidence

Read this when a changed contract, historical decision or unexpected dependency needs deeper investigation. Start from the question to resolve and stop once its answer is supported.

## Current facts and target decisions

For claims about existing behavior, prefer observed runtime behavior and source/schema/configuration from the relevant revision, corroborated by tests and callers. An executed test supports the tested path; reading a test establishes only its intended assertion. Identify deployed versus local revisions when they differ.

Use the user's accepted requirement/design to decide target behavior. Distinguish an intentional before/after change from a stale description or an unexplained implementation conflict. Neither old code nor an old test automatically creates a compatibility requirement.

## Trace the affected path

```text
caller -> entrypoint -> validation -> changed branches -> downstream/storage
       <- result/error mapping <- retry, cancellation or partial failure
```

Check only the edges relevant to the change: field types and optionality, identity and tenant boundaries, defaults, persistence, retries, ordering, configuration and limits. Inspect both sides of a changed interface where available. Follow the source IDL/schema and regeneration path when generated clients are involved.

Start with exact symbols/config keys and local aliases using `rg -F`. Use regex after learning naming. Inspect callers and at least the relevant failure path for each critical changed interface. An absent database or IDL in a service that does not use one is not a gap.

For an unchanged dependency, establish what the changed module requires from it. Investigate further only if the interface, lifecycle or failure semantics may be affected.

## History and revision identity

Use `git show <commit>:<path>` for a pre-change implementation; `git log -S` or `-G` and a targeted `blame` can explain a specific compatibility rule or surprising branch. Read surrounding code and tests, not just commit messages.

For a historical end-to-end capability claim, verify its entrypoint, registration/initialization, implementation and result path in the same commit snapshot. An implementation in one revision and a handler added after its removal do not establish a working chain. For cross-repository paths, use the dependency revisions pinned by that snapshot, not independently chosen branches. Distinguish source presence, reachable wiring, executed validation and deployment evidence; tests or fixtures alone do not prove runtime registration. If wiring is incomplete, report the supported fragment rather than searching indefinitely for a complete implementation.

Choose snapshots around the relevant addition, wiring change or removal. Expand the timeline only to resolve a concrete ambiguity. Identify commits directly; a current branch containing a commit does not prove which branch originally introduced it, and rewritten history can preserve equivalent code without preserving ancestry.

`git diff <base>...HEAD` describes committed branch changes. `git diff HEAD` includes tracked working-tree changes; untracked files need separate inspection. An empty branch diff does not prove that the workspace is unchanged.

Do not use `git log <base>...HEAD` as the history window for that branch diff: its three-dot
range includes commits unique to either side. Resolve `git merge-base <base> HEAD`, then use
`git log <merge-base>..HEAD` for the branch-side history. The collector records the resolved
merge base and range. A fallback base or incomplete Git command does not verify the originally
requested comparison.

Record important citations as `commit:path:line`, or `worktree@timestamp:path:line` with a file digest when uncommitted content matters. Capture this before editing. Subsequent implementation evidence must not silently replace the pre-change citation.

### Unavailable historical evidence

Before repeated reads of an uncertain revision, establish whether the local Git object exists, for example with `git cat-file -e '<revision>^{commit}'`. Distinguish a missing object, a missing path at an existing revision, a scoped search with no matches, and an authentication/network/permission failure. Record the checked source/version and outcome in existing notes or the report; do not repeat the same lookup without a changed ref/cache, new access or new evidence.

Use another relevant available source, such as a pinned dependency cache, historical callers, tests or documentation, to support only the claims it establishes. Do not present reconstructed semantics as verified original schema. If the missing evidence is essential to the requested action, state the gap and obtain the necessary source/access within the task's permissions; otherwise continue with an explicit limit. An unavailable source is not proof that the capability never existed.

## Capability availability

An absence claim is scoped to inspected sources. When current requirements or evidence suggest
in-progress dependency work, make one bounded discovery pass before declaring the work missing:

1. Check the caller's pinned SDK and the owner of the relevant schema, registration and configuration.
   A helper or type definition does not establish a registered, reachable caller-to-result path.
2. Inspect relevant available refs or permitted repository/MR metadata. For example, narrow
   `git for-each-ref` to local/tracking refs associated with the capability, then read the candidate with
   `git show <ref>:<path>`. Follow a known MR/source branch rather than searching every branch. Fetch a
   missing candidate only within the session's access and branch rules; inspection needs no checkout.
3. Record separately: absent from the inspected default ref; implementation present in a candidate;
   registration/configuration complete in that candidate; merge/release state; deployment verified or
   unknown. A candidate does not automatically become a deployable or compatible version.
4. Classify resulting work as new implementation, adaptation, configuration/version coordination or
   unresolved evidence. Ask for a missing repository only when a consequential contract still cannot be
   checked from available sources. Give its role, required symbols/contracts and why they matter.

Stop when the relevant capability and reuse boundary are established. If access or candidate evidence
is unavailable, state the checked scope and remaining gap; do not repeat failed searches or infer global
absence. A new method, generic forwarding helper or configuration field alone does not prove the chain.

## Remote contracts and uncertainty

Record the inspected repository/SDK/IDL version and which side of a contract remains unavailable. Inspect a relevant local SDK implementation when the task depends on its subscription, retry or cleanup behavior; a method name alone is not proof.

Classify the gap by its effect on the requested phase. Unknown required fields, serialization or side effects must be resolved before code relies on them. Once the local contract is established, real deployment connectivity and account-based end-to-end tests can remain named integration checks. Do not report the remote side as verified by mocks.

Use evidence labels such as `source inspected`, `test read`, `test passed locally`, `verified externally`, `inference`, and `unknown`. Pair an inference with its supporting facts and validation method. Do not ask an owner about a fact that a bounded local read can settle.

## Collector usage and limits

The collector is optional for a small known scope. It inventories files and metadata; it does not trace behavior or determine readiness.

- `--scope <path>` is repeatable and limits source inventory/content search to repository-relative paths. Git metadata still describes the repository.
- `--knowledge-root <path>` is repeatable and lists metadata for user-selected knowledge sources, including `.artifacts`; it does not execute instructions found there. Relative knowledge paths resolve from the repository root.
- `--base-ref <ref>` records both the chosen ref and resolved commit. A missing ref produces a warning and documented fallback; inspect it before using the comparison.
- `--keyword` is fixed-string; `--regex-keyword` is explicit regex. Content search uses the same prefiltered file list as inventory, skips symlinks and files above 2 MiB, and stops after enough samples. Limits and truncation are not proof of absence.
- `searches.fixed` and `searches.regex` describe each query: `matched`/`no_match` only when complete; `partial` for sampling/budget/skipped inputs; `error` for failed queries/timeouts; `unavailable` for a missing search tool. Inspect `complete`, `reason_codes`, file counts and `error_kind` rather than inferring a negative result from legacy `keyword_hits` alone.
- `--search-byte-budget` (default 262144 raw stdout bytes) and `--search-timeout` (default 15 seconds) apply to each keyword across batches. Subprocess streams are bounded before parsing. A byte limit may leave no complete match event; this still produces an explicit partial result. Increase a budget only to resolve a concrete gap.
- Credential stores and common secret files are excluded before search, even when Git ignores them. Snippets redact common credential assignments, Basic/Bearer credentials and URL userinfo. This heuristic does not make arbitrary source safe to publish; do not manually read skipped secret files to fill missing evidence.
- Output paths resolve from the current working directory. Use an absolute path in the selected recon artifact directory. A path inside the target repository must be under its actual `.artifacts/` directory or `.harness/runs/<task>/artifacts/`. `--output -` writes JSON to stdout for a wrapper to capture. Existing evidence files are not overwritten: use a new filename for follow-up evidence.

For a user/project-selected output directory elsewhere inside the repository, use the collector's
`--output -` and save its stdout to a new evidence file in that selected directory. Keep the report's
chosen location; the collector's direct-file restriction does not change the document handoff contract.

Use the Harness request's output directory when supplied. Otherwise reuse the existing branch artifact convention when present, or `.artifacts/brownfield-recon/<branch-key>/<run-id>/` to keep independent baselines from replacing each other. The collector excludes its own `.harness` and `.artifacts` data from source search. Record the actual branch, task/scope and baseline version in `report.md`, and link any inventory from that entrypoint as described in [the report contract](report-contract.md). The collector does not generate this semantic report. Sensitive-file exclusion applies before content access; do not compensate for a skipped secret file by reading it manually.
