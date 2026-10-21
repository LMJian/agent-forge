# Development branch consent

Default to the current branch and checkout, including existing uncommitted work. Do not create or
switch development branches, move to a detached revision, or create another development worktree
unless the user explicitly requests it or agrees after the purpose and target are explained.
An ordinary implementation request, `codex/` naming convention, clean-tree preference, autonomous
mode, design approval or `isolation=worktree` configuration does not grant this permission.
Read-only inspection of other refs (`git show`, `git diff`) does not change the development checkout.
Disposable repositories created solely by tests are test data, not alternate development branches.

For a needed exception, prepare a concrete target and preserve existing work before asking. Reuse
an applicable explicit request; do not ask again. Record it before the mutation:

```text
authorize-branch --module MODULE --actor user --note '<actual worktree approval>'
authorize-branch --branch EXACT_NAME --actor user --note '<actual branch request>'
```

These commands record consent; they do not grant it or switch Git. A module record applies only to
that task/module/implementation epoch. After replanning, record an existing still-applicable user
decision again; do not ask again unless its agreed target or purpose materially changes.
`prepare-module` blocks builtin creation and native host requests without that record;
`attach-worktree` verifies it again. Naming a detached checkout must be approved before the Git
operation, then `bind-branch` verifies the exact name and commit. Shell commands outside Harness
are governed by the same agent rule; the runtime cannot intercept arbitrary external Git calls.

If no consent exists, continue in the current checkout. Prefer one module so this remains practical.
If isolation is essential and cannot proceed safely, explain that concrete need and await consent.
