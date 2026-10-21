"""Exercise consent through real disposable Git repositories, never the development branch."""
from harness import branches, guidance, worktrees
from harness.model import HarnessError, default_config, resolve_workflow
from harness.storage import atomic_json, read_json
from test_workflow import RepoCase
import test_host_execution as support


class BranchConsentTests(RepoCase):
    cli = support.PortableExecutionTests.cli

    def ready_without_branch_consent(self):
        self.to_approval()
        self.flow.approve("design_approval", "fixture-user", "Approve design only")
        self.flow.skip("interfaces", "No interfaces")
        path = self.root / ".harness/runs/example/artifacts/plan.json"
        atomic_json(path, {"core": [{"id": "build", "summary": "Add value", "acceptance": ["AC-1"], "verification": "Observe value"}]})
        self.flow.plan(str(path))
        self.flow.enter("implement")

    def test_default_checkout_keeps_current_branch_and_needs_no_consent(self):
        self.assertEqual(resolve_workflow(default_config())["isolation"], "checkout")
        self.flow.configure_flow({"isolation": "checkout"}, "Develop on the existing branch")
        self.ready_without_branch_consent()
        before = self.git("symbolic-ref", "HEAD")
        module = worktrees.prepare(self.flow, "core")
        self.assertEqual(module["worktree"], str(self.root))
        self.assertEqual(self.git("symbolic-ref", "HEAD"), before)
        self.assertFalse(self.flow.load().get("branch_authorizations"))

    def test_design_approval_does_not_authorize_worktree(self):
        self.ready_without_branch_consent()
        before = self.git("worktree", "list", "--porcelain")
        refs = self.git("for-each-ref", "--format=%(refname)")
        self.assertEqual(guidance.advance(self.flow)["action"]["scope"], "branch")
        with self.assertRaisesRegex(HarnessError, "explicit user approval"):
            worktrees.prepare(self.flow, "core")
        self.assertEqual(self.git("worktree", "list", "--porcelain"), before)
        self.assertEqual(self.git("for-each-ref", "--format=%(refname)"), refs)

    def test_actual_consent_allows_only_selected_module_epoch(self):
        self.ready_without_branch_consent()
        with self.assertRaisesRegex(HarnessError, "actual user"):
            branches.authorize(self.flow, actor="codex", note="Looks convenient", module="core")
        self.cli("authorize-branch", "--module", "core", "--actor", "user", "--note", "Fixture user explicitly approves a core worktree")
        module = worktrees.prepare(self.flow, "core")
        self.assertNotEqual(module["worktree"], str(self.root))
        self.flow.reopen("implement", "Retry in a new implementation epoch")
        self.assertIsNone(branches.approved(self.flow.load(), module="core"))

    def test_native_worktree_request_also_requires_consent(self):
        path = self.root / '.harness/project.json'
        config = read_json(path)
        config['host']['available'] = ['worktree']
        atomic_json(path, config)
        self.flow.sync_config('Exercise the native worktree provider')
        self.ready_without_branch_consent()
        # The approval gate is before either native request creation or builtin Git mutation.
        with self.assertRaisesRegex(HarnessError, "explicit user approval"):
            worktrees.prepare(self.flow, "core")
        self.assertNotIn("request", self.flow.load()["modules"]["core"])

    def test_detached_branch_binding_cannot_invent_after_the_fact_consent(self):
        self.flow.abort('Use a disposable detached fixture')
        self.git('checkout', '--detach')
        from harness.engine import Workflow
        self.flow = Workflow(self.root, 'detached-no-consent')
        self.flow.start('Inspect detached work', options={'isolation': 'checkout'})
        self.git('switch', '-c', 'unapproved-fixture-branch')
        with self.assertRaisesRegex(HarnessError, 'explicit user approval'):
            self.flow.bind_branch('An implementation request is not consent')
        with self.assertRaisesRegex(HarnessError, 'owning checkout'):
            branches.authorize(self.flow, actor='user', note='Too late for pre-action consent', branch='unapproved-fixture-branch')
