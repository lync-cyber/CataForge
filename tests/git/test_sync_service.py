"""Decision-matrix tests for the git-hygiene service.

Driven by :class:`FakeGitWorkTree` so each branch of the fetch/FF/prune
logic is pinned by *which port methods fire* — including strong negative
assertions that no mutation happens on the refuse paths.
"""

from __future__ import annotations

import pytest

from cataforge.application.services.git_hygiene import (
    find_merged_branches,
    prune_branches,
    sync_default_branch,
)
from cataforge.core.errors import CataforgeError
from tests.support.gitrepo import FakeGitWorkTree


class TestSyncDecision:
    def test_clean_and_behind_fast_forwards(self) -> None:
        fake = FakeGitWorkTree(clean=True, ahead=0, behind=2)
        outcome = sync_default_branch(fake)
        assert outcome.action == "fast-forwarded"
        assert outcome.behind == 2
        assert outcome.switched_from is None
        assert ("merge_ff_only", "origin/main") in fake.calls

    def test_up_to_date_does_not_fast_forward(self) -> None:
        fake = FakeGitWorkTree(ahead=0, behind=0)
        outcome = sync_default_branch(fake)
        assert outcome.action == "up-to-date"
        assert "merge_ff_only" not in fake.method_names

    def test_ahead_only_skips_fast_forward(self) -> None:
        fake = FakeGitWorkTree(ahead=1, behind=0)
        outcome = sync_default_branch(fake)
        assert outcome.action == "ahead-skip"
        assert outcome.ahead == 1
        assert "merge_ff_only" not in fake.method_names

    def test_diverged_raises_without_merging(self) -> None:
        fake = FakeGitWorkTree(ahead=1, behind=1)
        with pytest.raises(CataforgeError, match="diverged"):
            sync_default_branch(fake)
        assert "merge_ff_only" not in fake.method_names

    def test_switches_from_feature_branch_then_fast_forwards(self) -> None:
        fake = FakeGitWorkTree(current="feat/x", default="main", clean=True, behind=3)
        outcome = sync_default_branch(fake)
        assert outcome.switched_from == "feat/x"
        assert ("switch", "main") in fake.calls
        # switch must precede the fast-forward.
        assert fake.method_names.index("switch") < fake.method_names.index("merge_ff_only")
        assert outcome.action == "fast-forwarded"

    def test_dirty_tree_needing_switch_raises_before_any_mutation(self) -> None:
        fake = FakeGitWorkTree(current="feat/x", default="main", clean=False, behind=3)
        with pytest.raises(CataforgeError, match="uncommitted"):
            sync_default_branch(fake)
        assert "switch" not in fake.method_names
        assert "merge_ff_only" not in fake.method_names

    def test_detached_head_raises_before_fetch(self) -> None:
        fake = FakeGitWorkTree(current="HEAD")
        with pytest.raises(CataforgeError, match="[Dd]etached"):
            sync_default_branch(fake)
        assert "fetch_prune" not in fake.method_names


class TestPruneService:
    def test_find_merged_excludes_target_and_head(self) -> None:
        fake = FakeGitWorkTree(
            locals_=["main", "feat/done", "feat/wip"],
            merged={"main", "feat/done", "HEAD"},
        )
        assert find_merged_branches(fake, "main") == ["feat/done"]

    def test_prune_deletes_each_with_safe_flag(self) -> None:
        fake = FakeGitWorkTree()
        deleted, failed = prune_branches(fake, ["a", "b"])
        assert deleted == ["a", "b"]
        assert failed == []
        assert ("delete_branch", "a", False) in fake.calls
        assert ("delete_branch", "b", False) in fake.calls

    def test_prune_collects_failures_without_aborting_batch(self) -> None:
        fake = FakeGitWorkTree(fail_delete={"b"})
        deleted, failed = prune_branches(fake, ["a", "b", "c"])
        assert deleted == ["a", "c"]
        assert [name for name, _ in failed] == ["b"]
