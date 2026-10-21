"""Explicit, task-scoped user consent before changing the development checkout."""
from . import git as vcs
from .model import nonempty, now, require
from .storage import file_lock


def scope(state, *, module=None, branch=None):
    require((module is None) != (branch is None), "Choose a module worktree or a named branch")
    if module is not None:
        require(module in state["modules"], "Approve a planned module, not a future wildcard")
        return {"operation": "worktree", "module": module,
                "epoch": state["stages"]["implement"]["epoch"]}
    nonempty(branch, "branch")
    require(not branch.startswith("-"), "Invalid branch name")
    return {"operation": "branch", "branch": branch}


def approved(state, *, module=None, branch=None):
    selected = scope(state, module=module, branch=branch)
    return next((a for a in reversed(state.get("branch_authorizations", []))
                 if a["scope"] == selected and a["owning_branch"] == state["branch"]), None)


def require_approval(state, *, module=None, branch=None):
    receipt = approved(state, module=module, branch=branch)
    require(receipt is not None,
            "Branch/worktree development requires explicit user approval; default to the current checkout. "
            "Record the actual decision with authorize-branch before creating or switching it")
    return receipt


def authorize(workflow, *, actor, note, module=None, branch=None):
    require(actor == "user", "Branch authorization must record the actual user's decision")
    nonempty(note, "note (quote the user's explicit branch/worktree approval)")
    with file_lock(workflow.lock_path):
        state = workflow.load(active=False)
        require(not state["aborted"], "Cannot authorize an aborted task")
        selected = scope(state, module=module, branch=branch)
        if branch is not None:
            vcs.git(workflow.root, "check-ref-format", "--branch", branch)
        receipt = {"scope": selected, "actor": actor, "note": note, "at": now(),
                   "owning_branch": state["branch"], "head": vcs.head(workflow.root)}
        state.setdefault("branch_authorizations", []).append(receipt)
        workflow.save(state, "branch_authorized", scope=selected)
        return receipt
