"""sprint-review project_features — dev-plan frontmatter knobs.

Covers the three checker upgrades introduced for #106 EXP-003 + EXP-008:

* ``merged_review`` — short-circuit per-task ``code_review_present``.
* ``deliverables_accept_alternation`` — ``A | B`` deliverable lines pass
  when either path exists.
* ``unplanned_glob_patterns`` — fnmatch whitelist removes matched files
  from the unplanned-files WARN set.

Loader (``load_project_features``) ignores sprint volumes (``-s{N}.md``)
and reads the first main dev-plan file with a ``project_features:``
frontmatter block.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cataforge.skill.builtins.sprint_review.ignore import build_ignore_spec
from cataforge.skill.builtins.sprint_review.sprint_check import (
    check_code_reviews,
    check_deliverables,
    check_unplanned_files,
    load_project_features,
)

# ---------------------------------------------------------------------------
# load_project_features
# ---------------------------------------------------------------------------


class TestLoadProjectFeatures:
    def test_returns_empty_when_no_frontmatter(self, tmp_path: Path) -> None:
        f = tmp_path / "dev-plan-foo.md"
        f.write_text("# dev-plan\nno frontmatter here.\n", encoding="utf-8")
        assert load_project_features([str(f)]) == {}

    def test_returns_empty_when_no_project_features_key(
        self, tmp_path: Path
    ) -> None:
        f = tmp_path / "dev-plan-foo.md"
        f.write_text(
            "---\nid: dev-plan-foo\nversion: '0.1.0'\n---\n# title\n",
            encoding="utf-8",
        )
        assert load_project_features([str(f)]) == {}

    def test_loads_features_from_main_volume(self, tmp_path: Path) -> None:
        f = tmp_path / "dev-plan-foo.md"
        f.write_text(
            "---\n"
            "id: dev-plan-foo\n"
            "project_features:\n"
            "  merged_review: true\n"
            "  deliverables_accept_alternation: true\n"
            "  unplanned_glob_patterns:\n"
            "    - '**/*.test.ts'\n"
            "    - '**/helpers/*.py'\n"
            "---\n# title\n",
            encoding="utf-8",
        )
        feats = load_project_features([str(f)])
        assert feats["merged_review"] is True
        assert feats["deliverables_accept_alternation"] is True
        assert feats["unplanned_glob_patterns"] == [
            "**/*.test.ts", "**/helpers/*.py",
        ]

    def test_skips_sprint_volumes(self, tmp_path: Path) -> None:
        sprint = tmp_path / "dev-plan-foo-s1.md"
        sprint.write_text(
            "---\nproject_features:\n  merged_review: true\n---\n",
            encoding="utf-8",
        )
        # Only sprint volume present → loader returns empty (won't read s-volume).
        assert load_project_features([str(sprint)]) == {}

        main = tmp_path / "dev-plan-foo.md"
        main.write_text(
            "---\nproject_features:\n  merged_review: false\n---\n",
            encoding="utf-8",
        )
        # Both present → main wins, even if main says false.
        feats = load_project_features([str(sprint), str(main)])
        assert feats == {"merged_review": False}


# ---------------------------------------------------------------------------
# check_code_reviews — merged_review short-circuit
# ---------------------------------------------------------------------------


class TestCheckCodeReviewsMergedReview:
    def test_default_flags_missing_reports(self, tmp_path: Path) -> None:
        reviews = tmp_path / "reviews"
        reviews.mkdir()
        tasks = [{"id": "T-001"}, {"id": "T-002"}]
        issues = check_code_reviews(tasks, str(reviews))
        assert len(issues) == 2
        assert all(i["category"] == "code_review_present" for i in issues)

    def test_merged_review_short_circuits(self, tmp_path: Path) -> None:
        reviews = tmp_path / "reviews"
        reviews.mkdir()
        tasks = [{"id": "T-001"}, {"id": "T-002"}]
        assert check_code_reviews(tasks, str(reviews), merged_review=True) == []

    def test_merged_review_skips_missing_dir_warning(
        self, tmp_path: Path
    ) -> None:
        # Even when dir doesn't exist, merged_review skips the warn.
        nonexistent = tmp_path / "nope"
        assert check_code_reviews(
            [{"id": "T-001"}], str(nonexistent), merged_review=True
        ) == []


# ---------------------------------------------------------------------------
# check_deliverables — accept_alternation
# ---------------------------------------------------------------------------


class TestCheckDeliverablesAlternation:
    def test_alternation_passes_when_any_exists(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "foo.tsx").write_text("", encoding="utf-8")
        # foo.ts missing, foo.tsx present → A | B passes when alternation enabled.
        tasks = [{
            "id": "T-1",
            "deliverables": [
                str(tmp_path / "src" / "foo.ts")
                + " | " + str(tmp_path / "src" / "foo.tsx"),
            ],
        }]
        assert check_deliverables(tasks, accept_alternation=True) == []

    def test_alternation_fails_when_both_missing(self, tmp_path: Path) -> None:
        tasks = [{
            "id": "T-1",
            "deliverables": [
                str(tmp_path / "missing-a.ts")
                + " | " + str(tmp_path / "missing-b.ts"),
            ],
        }]
        issues = check_deliverables(tasks, accept_alternation=True)
        assert len(issues) == 1
        assert "所有候选均缺失" in issues[0]["message"]

    def test_alternation_disabled_treats_pipe_as_literal(
        self, tmp_path: Path
    ) -> None:
        # Default behavior: literal "A | B" is one missing path.
        tasks = [{
            "id": "T-1",
            "deliverables": [
                str(tmp_path / "src" / "foo.ts")
                + " | " + str(tmp_path / "src" / "foo.tsx"),
            ],
        }]
        issues = check_deliverables(tasks)
        assert len(issues) == 1
        assert "交付物缺失" in issues[0]["message"]


# ---------------------------------------------------------------------------
# check_unplanned_files — glob_whitelist
# ---------------------------------------------------------------------------


class TestCheckUnplannedFilesWhitelist:
    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        src = tmp_path / "src"
        src.mkdir()
        (src / "feature.ts").write_text("", encoding="utf-8")
        (src / "feature.test.ts").write_text("", encoding="utf-8")
        helpers = src / "helpers"
        helpers.mkdir()
        (helpers / "util.ts").write_text("", encoding="utf-8")
        return tmp_path

    def _check(self, project: Path, **kwargs):  # noqa: ANN003
        ignore_spec = build_ignore_spec(use_defaults=True)
        return check_unplanned_files(
            [{"id": "T-1", "deliverables": [str(project / "src" / "feature.ts")]}],
            [str(project / "src")],
            respect_gitignore=False,
            ignore_spec=ignore_spec,
            **kwargs,
        )

    def test_no_whitelist_flags_test_and_helper(self, project: Path) -> None:
        issues = self._check(project)
        paths = sorted(i["path"] for i in issues)
        assert any("feature.test.ts" in p for p in paths)
        assert any("helpers" in p for p in paths)

    def test_whitelist_filters_test_files(self, project: Path) -> None:
        issues = self._check(project, glob_whitelist=["**/*.test.ts"])
        paths = sorted(i["path"] for i in issues)
        # test file gone, helper remains.
        assert not any("feature.test.ts" in p for p in paths)
        assert any("helpers" in p for p in paths)

    def test_whitelist_filters_helper_dir(self, project: Path) -> None:
        issues = self._check(project, glob_whitelist=["**/helpers/*"])
        paths = sorted(i["path"] for i in issues)
        # helper gone, test remains.
        assert not any("helpers" in p for p in paths)
        assert any("feature.test.ts" in p for p in paths)

    def test_whitelist_combines(self, project: Path) -> None:
        issues = self._check(
            project, glob_whitelist=["**/*.test.ts", "**/helpers/*"]
        )
        # Both filtered; only feature.ts (planned) remains, so issues empty.
        assert issues == []

    def test_alternation_deliverable_counts_both_as_planned(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "foo.ts").write_text("", encoding="utf-8")
        (src / "foo.tsx").write_text("", encoding="utf-8")
        ignore_spec = build_ignore_spec(use_defaults=True)
        issues = check_unplanned_files(
            [{
                "id": "T-1",
                "deliverables": [
                    str(src / "foo.ts") + " | " + str(src / "foo.tsx"),
                ],
            }],
            [str(src)],
            respect_gitignore=False,
            ignore_spec=ignore_spec,
        )
        # Neither alternative should be flagged as unplanned.
        paths = [i["path"] for i in issues]
        assert all("foo." not in p for p in paths)
