"""find_prunable_branches — the squash-aware deletion decision.

Pure decision tests on a scripted port + gh stub: a branch is deletable
only when its upstream is gone *and* (optionally) gh confirms a merged PR.
The current and default branches are never candidates.
"""

from __future__ import annotations

from cataforge.application.services.git_hygiene import find_prunable_branches, prune_branches
from tests.support.gitrepo import FakeGitHubRepo, FakeGitWorkTree


def _verdict(verdicts, name):
    return next(v for v in verdicts if v.branch == name)


class TestPruneDecision:
    def test_gone_and_pr_merged_is_deletable(self) -> None:
        git = FakeGitWorkTree(current="main", locals_=["main", "feat/x"], gone={"feat/x"})
        gh = FakeGitHubRepo(merged={"feat/x"})
        verdicts = find_prunable_branches(git, gh, default_branch="main", confirm_via_gh=True)
        v = _verdict(verdicts, "feat/x")
        assert v.deletable is True
        assert v.upstream_gone is True
        assert v.pr_merged is True

    def test_gone_but_pr_not_merged_is_kept(self) -> None:
        git = FakeGitWorkTree(current="main", locals_=["main", "feat/x"], gone={"feat/x"})
        gh = FakeGitHubRepo(merged=set())  # remote branch vanished, but no merged PR
        verdicts = find_prunable_branches(git, gh, default_branch="main", confirm_via_gh=True)
        v = _verdict(verdicts, "feat/x")
        assert v.deletable is False
        assert v.upstream_gone is True
        assert v.pr_merged is False

    def test_not_gone_is_kept(self) -> None:
        git = FakeGitWorkTree(current="main", locals_=["main", "feat/active"], gone=set())
        gh = FakeGitHubRepo()
        verdicts = find_prunable_branches(git, gh, default_branch="main", confirm_via_gh=True)
        v = _verdict(verdicts, "feat/active")
        assert v.deletable is False
        assert v.upstream_gone is False
        assert gh.calls == []  # no gh probe for a branch that still has an upstream

    def test_confirm_disabled_trusts_gone(self) -> None:
        git = FakeGitWorkTree(current="main", locals_=["main", "feat/x"], gone={"feat/x"})
        gh = FakeGitHubRepo(merged=set())
        verdicts = find_prunable_branches(git, gh, default_branch="main", confirm_via_gh=False)
        v = _verdict(verdicts, "feat/x")
        assert v.deletable is True
        assert gh.calls == []  # gh never consulted when confirmation is disabled

    def test_current_branch_never_pruned(self) -> None:
        git = FakeGitWorkTree(current="feat/x", locals_=["main", "feat/x"], gone={"feat/x"})
        gh = FakeGitHubRepo(merged={"feat/x"})
        verdicts = find_prunable_branches(git, gh, default_branch="main", confirm_via_gh=True)
        assert all(v.branch != "feat/x" for v in verdicts)

    def test_default_branch_never_pruned(self) -> None:
        git = FakeGitWorkTree(current="feat/x", locals_=["main", "feat/x"], gone={"main"})
        gh = FakeGitHubRepo()
        verdicts = find_prunable_branches(git, gh, default_branch="main", confirm_via_gh=False)
        assert all(v.branch != "main" for v in verdicts)


class TestPruneBatch:
    def test_force_deletes_each(self) -> None:
        git = FakeGitWorkTree()
        deleted, failed = prune_branches(git, ["a", "b"])
        assert deleted == ["a", "b"]
        assert failed == []
        # -D, not -d: squash-merged branches are not ancestors of the default.
        assert ("delete_branch", "a", True) in git.calls
        assert ("delete_branch", "b", True) in git.calls

    def test_collects_failures_without_aborting_batch(self) -> None:
        git = FakeGitWorkTree(fail_delete={"b"})
        deleted, failed = prune_branches(git, ["a", "b", "c"])
        assert deleted == ["a", "c"]
        assert [name for name, _ in failed] == ["b"]
