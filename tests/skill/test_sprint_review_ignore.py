"""sprint-review unplanned-file detection — ignore + git integration.

Covers the four PRs bundled into the noise-fix:

- PR1: ``IgnoreSpec`` + ``DEFAULT_IGNORE_PATTERNS`` — node_modules / dist /
  *.tsbuildinfo / __pycache__ are silenced, real source files still surface.
- PR2: ``list_candidate_files`` — when in a git repo, candidates come from
  ``git ls-files -co --exclude-standard`` (gitignore is honoured automatically).
- PR3: text renderer's ``--warn-cap`` folding + ``--unplanned-log`` dump +
  ``--format json`` structured output.
- PR4: ``CHECKS_MANIFEST`` IDs match the ones the script actually emits.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cataforge.skill.builtins.sprint_review import CHECKS_MANIFEST
from cataforge.skill.builtins.sprint_review.ignore import (
    DEFAULT_IGNORE_PATTERNS,
    IgnoreSpec,
    build_ignore_spec,
    git_list_files,
    is_git_repo,
    list_candidate_files,
)
from cataforge.skill.builtins.sprint_review.sprint_check import (
    _aggregate_unplanned,
    check_unplanned_files,
)

# ---------------------------------------------------------------------------
# IgnoreSpec — pattern matcher
# ---------------------------------------------------------------------------


class TestIgnoreSpec:
    def test_dir_segment_match_anywhere(self) -> None:
        spec = IgnoreSpec(["node_modules/"])
        assert spec.match("packages/a/node_modules/zod/index.js")
        assert spec.match("node_modules/foo.js")
        assert not spec.match("packages/a/src/index.ts")

    def test_basename_glob(self) -> None:
        spec = IgnoreSpec(["*.tsbuildinfo", "*.map"])
        assert spec.match("packages/a/dist/x.js.map")
        assert spec.match("packages/a/tsconfig.tsbuildinfo")
        assert not spec.match("packages/a/src/x.ts")

    def test_path_glob_with_slash(self) -> None:
        spec = IgnoreSpec(["packages/*/dist/**"])
        assert spec.match("packages/skill/dist/index.js")

    def test_blank_and_comment_ignored(self) -> None:
        spec = IgnoreSpec(["", "  ", "# comment", "node_modules/"])
        assert spec.match("node_modules/x.js")

    def test_default_patterns_silence_common_artifacts(self) -> None:
        spec = build_ignore_spec(use_defaults=True)
        for noise in (
            "packages/a/node_modules/zod/index.js",
            "packages/a/dist/index.d.ts",
            "packages/a/tsconfig.tsbuildinfo",
            "packages/a/dist/index.js.map",
            "src/foo/__pycache__/bar.pyc",
            ".venv/lib/x.py",
            ".pytest_cache/v/cache/lastfailed",
        ):
            assert spec.match(noise), f"expected default ignore to match: {noise}"

    def test_default_patterns_let_real_source_through(self) -> None:
        spec = build_ignore_spec(use_defaults=True)
        for keep in (
            "packages/skill/src/index.ts",
            "src/cataforge/cli/main.py",
            "tests/skill/test_x.py",
        ):
            assert not spec.match(keep), f"unexpectedly ignored: {keep}"

    def test_extra_patterns_extend_defaults(self) -> None:
        spec = build_ignore_spec(use_defaults=True, extra_patterns=["fixtures/"])
        assert spec.match("tests/fixtures/sample.json")
        assert spec.match("node_modules/x.js")  # defaults still applied

    def test_no_default_ignores(self) -> None:
        spec = build_ignore_spec(use_defaults=False)
        assert not spec.match("node_modules/x.js")

    def test_extra_file_loaded(self, tmp_path: Path) -> None:
        ig = tmp_path / "extra.ignore"
        ig.write_text("# header\nfixtures/\n*.bin\n", encoding="utf-8")
        spec = build_ignore_spec(use_defaults=False, extra_files=[str(ig)])
        assert spec.match("foo/fixtures/x.json")
        assert spec.match("data.bin")
        assert not spec.match("src/foo.py")


# ---------------------------------------------------------------------------
# Git integration — list_candidate_files
# ---------------------------------------------------------------------------


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, check=True,
        capture_output=True, text=True,
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Mini git repo with a planned src file + a node_modules + a dist."""
    try:
        subprocess.run(
            ["git", "--version"], capture_output=True, text=True, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("git not available")

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "test"], repo)
    _git(["config", "commit.gpgsign", "false"], repo)

    (repo / ".gitignore").write_text(
        "node_modules/\ndist/\n*.tsbuildinfo\n", encoding="utf-8",
    )
    src = repo / "packages" / "skill" / "src"
    src.mkdir(parents=True)
    (src / "index.ts").write_text("export {};\n", encoding="utf-8")
    # extra "unplanned" source file — should surface as gold-plating
    (src / "extra.ts").write_text("export const x = 1;\n", encoding="utf-8")

    nm = repo / "packages" / "skill" / "node_modules" / "zod"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("module.exports = {};\n", encoding="utf-8")

    dist = repo / "packages" / "skill" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.js").write_text("// build\n", encoding="utf-8")
    (repo / "packages" / "skill" / "tsconfig.tsbuildinfo").write_text(
        "{}\n", encoding="utf-8",
    )

    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "init"], repo)
    return repo


class TestGitIntegration:
    def test_is_git_repo(self, git_repo: Path) -> None:
        assert is_git_repo(str(git_repo))
        assert not is_git_repo(str(git_repo.parent / "nope"))

    def test_git_list_files_excludes_gitignored(self, git_repo: Path) -> None:
        files = git_list_files(["packages/skill"], cwd=str(git_repo))
        # tracked + untracked but-not-ignored only
        assert any(f.endswith("src/index.ts") for f in files)
        assert any(f.endswith("src/extra.ts") for f in files)
        assert not any("node_modules" in f for f in files)
        assert not any("/dist/" in f for f in files)
        assert not any(f.endswith(".tsbuildinfo") for f in files)

    def test_list_candidate_files_respects_gitignore_then_default(
        self, git_repo: Path
    ) -> None:
        spec = build_ignore_spec(use_defaults=True)
        files = list_candidate_files(
            ["packages/skill"],
            respect_gitignore=True,
            ignore_spec=spec,
            cwd=str(git_repo),
        )
        assert sorted(files) == [
            "packages/skill/src/extra.ts",
            "packages/skill/src/index.ts",
        ]

    def test_walk_fallback_with_default_ignores(
        self, git_repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # disable git integration → must rely on DEFAULT_IGNORE_PATTERNS
        spec = build_ignore_spec(use_defaults=True)
        monkeypatch.chdir(git_repo)
        files = list_candidate_files(
            ["packages/skill"],
            respect_gitignore=False,
            ignore_spec=spec,
        )
        # node_modules pruned + dist + tsbuildinfo ignored
        assert all("node_modules" not in f for f in files)
        assert all("/dist/" not in f for f in files)
        assert all(not f.endswith(".tsbuildinfo") for f in files)
        assert any(f.endswith("src/index.ts") for f in files)


# ---------------------------------------------------------------------------
# check_unplanned_files — end-to-end semantics
# ---------------------------------------------------------------------------


class TestCheckUnplannedFiles:
    def test_planned_file_passes_extra_warns(self, git_repo: Path) -> None:
        tasks = [{
            "id": "T-001",
            "deliverables": ["packages/skill/src/index.ts"],
        }]
        spec = build_ignore_spec(use_defaults=True)
        old = os.getcwd()
        os.chdir(git_repo)
        try:
            issues = check_unplanned_files(
                tasks, ["packages/skill"],
                respect_gitignore=True, ignore_spec=spec,
            )
        finally:
            os.chdir(old)

        # only extra.ts is unplanned — node_modules / dist / tsbuildinfo
        # all silenced by gitignore + default ignores
        assert [it["path"] for it in issues] == ["packages/skill/src/extra.ts"]
        assert all(it["severity"] == "warn" for it in issues)
        assert all(it["category"] == "unplanned_files" for it in issues)

    def test_deliverable_dir_covers_subtree(self, git_repo: Path) -> None:
        # if deliverable is a directory path, files under it aren't unplanned
        tasks = [{
            "id": "T-001",
            "deliverables": ["packages/skill/src"],
        }]
        spec = build_ignore_spec(use_defaults=True)
        old = os.getcwd()
        os.chdir(git_repo)
        try:
            issues = check_unplanned_files(
                tasks, ["packages/skill"],
                respect_gitignore=True, ignore_spec=spec,
            )
        finally:
            os.chdir(old)
        assert issues == []


# ---------------------------------------------------------------------------
# Renderer: warn-cap aggregation
# ---------------------------------------------------------------------------


class TestAggregateUnplanned:
    def _mk(self, n: int, prefix: str) -> list[dict]:
        return [
            {
                "severity": "warn", "category": "unplanned_files",
                "message": f"... {prefix}/{i}",
                "path": f"{prefix}/file{i}.txt",
            }
            for i in range(n)
        ]

    def test_no_folding_when_under_cap(self) -> None:
        issues = self._mk(10, "node_modules")
        visible, by_dir, hidden = _aggregate_unplanned(issues, cap=50)
        assert len(visible) == 10
        assert by_dir == {}
        assert hidden == 0

    def test_folds_excess_grouped_by_top_dir(self) -> None:
        issues = self._mk(20, "node_modules") + self._mk(5, "dist")
        visible, by_dir, hidden = _aggregate_unplanned(issues, cap=10)
        assert len(visible) == 10
        assert hidden == 15
        # the hidden 15 are the last 15 (10 NM + 5 dist)
        assert by_dir["node_modules"] == 10
        assert by_dir["dist"] == 5

    def test_cap_zero_disables_folding(self) -> None:
        issues = self._mk(100, "node_modules")
        visible, by_dir, hidden = _aggregate_unplanned(issues, cap=0)
        assert len(visible) == 100
        assert hidden == 0


# ---------------------------------------------------------------------------
# CLI smoke — JSON format + warn-cap log dump
# ---------------------------------------------------------------------------


def _make_dev_plan(repo: Path, sprint: int, deliverables: list[str]) -> None:
    plan = repo / "docs" / "dev-plan"
    plan.mkdir(parents=True)
    deliv_lines = "\n".join(f"    - {p}" for p in deliverables)
    (plan / f"plan-s{sprint}.md").write_text(
        f"# Plan\n\n## Sprint {sprint}\n\n"
        f"### T-001\n"
        f"- status: done\n"
        f"- deliverables:\n{deliv_lines}\n"
        f"- tdd_acceptance:\n    - AC-001\n",
        encoding="utf-8",
    )
    reviews = repo / "docs" / "reviews" / "code"
    reviews.mkdir(parents=True)
    (reviews / "CODE-REVIEW-T-001-r1.md").write_text("ok\n", encoding="utf-8")
    tests = repo / "tests"
    tests.mkdir()
    (tests / "test_x.py").write_text("# AC-001 covered\n", encoding="utf-8")


class TestCLIIntegration:
    def _run(self, repo: Path, *extra: str) -> subprocess.CompletedProcess:
        # PYTHONUTF8 forces the *child*'s stdio to UTF-8; passing
        # ``encoding="utf-8"`` decodes the captured bytes as UTF-8
        # regardless of the parent's locale (Windows CI defaults to
        # cp1252, which crashes the reader thread on Chinese / em-dash
        # output and leaves r.stdout = None).
        env = {**os.environ, "PYTHONUTF8": "1"}
        return subprocess.run(
            [
                sys.executable, "-m",
                "cataforge.skill.builtins.sprint_review.sprint_check",
                "1",
                "--dev-plan", "docs/dev-plan/",
                "--src-dir", "packages/skill",
                "--test-dir", "tests/",
                "--reviews-dir", "docs/reviews/code/",
                *extra,
            ],
            cwd=repo, capture_output=True, encoding="utf-8",
            errors="replace", env=env, timeout=60,
        )

    def test_json_format_emits_structured_payload(self, git_repo: Path) -> None:
        _make_dev_plan(git_repo, 1, ["packages/skill/src/index.ts"])
        r = self._run(git_repo, "--format", "json")
        assert r.returncode == 0, r.stdout + r.stderr
        payload = json.loads(r.stdout)
        assert payload["sprint"] == 1
        assert payload["tasks"] == ["T-001"]
        # only extra.ts surfaces; node_modules/dist/tsbuildinfo silenced
        unplanned = [
            it for it in payload["issues"]
            if it["category"] == "unplanned_files"
        ]
        assert [it["path"] for it in unplanned] == [
            "packages/skill/src/extra.ts"
        ]
        assert payload["summary"]["fail"] == 0

    def test_warn_cap_writes_unplanned_log(self, git_repo: Path) -> None:
        _make_dev_plan(git_repo, 1, ["packages/skill/src/index.ts"])
        log = git_repo / "out" / "unplanned.txt"
        r = self._run(
            git_repo, "--warn-cap", "0",
            "--unplanned-log", str(log),
        )
        assert r.returncode == 0, r.stdout + r.stderr
        assert log.is_file()
        body = log.read_text(encoding="utf-8")
        assert "packages/skill/src/extra.ts" in body
        assert "node_modules" not in body  # gitignore honoured

    def test_repeatable_src_dir(self, git_repo: Path) -> None:
        # add a second package with no extra files
        pkg2 = git_repo / "packages" / "shared-types" / "src"
        pkg2.mkdir(parents=True)
        (pkg2 / "index.ts").write_text("export {};\n", encoding="utf-8")
        _git(["add", "."], git_repo)
        _git(["commit", "-q", "-m", "add shared-types"], git_repo)

        _make_dev_plan(git_repo, 1, [
            "packages/skill/src/index.ts",
            "packages/shared-types/src/index.ts",
        ])
        r = subprocess.run(
            [
                sys.executable, "-m",
                "cataforge.skill.builtins.sprint_review.sprint_check",
                "1",
                "--dev-plan", "docs/dev-plan/",
                "--src-dir", "packages/skill/src",
                "--src-dir", "packages/shared-types/src",
                "--test-dir", "tests/",
                "--reviews-dir", "docs/reviews/code/",
                "--format", "json",
            ],
            cwd=git_repo, capture_output=True, encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONUTF8": "1"}, timeout=60,
        )
        assert r.returncode == 0, r.stdout + r.stderr
        payload = json.loads(r.stdout)
        unplanned = [
            it for it in payload["issues"]
            if it["category"] == "unplanned_files"
        ]
        # extra.ts in skill is the only file outside both deliverables
        assert [it["path"] for it in unplanned] == [
            "packages/skill/src/extra.ts"
        ]


# ---------------------------------------------------------------------------
# Manifest contract (PR4)
# ---------------------------------------------------------------------------


class TestManifestContract:
    def test_manifest_ids_match_emitted_categories(self) -> None:
        manifest_ids = {entry["id"] for entry in CHECKS_MANIFEST}
        # every category sprint_check emits as a real check should have a
        # corresponding manifest id (boundary error categories like
        # dev_plan_missing / sprint_tasks_missing are not Layer 1 checks)
        emitted = {
            "task_status_done",
            "deliverables_exist",
            "ac_coverage",
            "unplanned_files",
            "code_review_present",
        }
        assert emitted == manifest_ids

    def test_default_ignore_list_covers_known_offenders(self) -> None:
        # regression guard: shrinking DEFAULT_IGNORE_PATTERNS would re-noise
        # the original bug
        for required in (
            "node_modules/", "dist/", "build/", "*.tsbuildinfo", "*.map",
            "__pycache__/", ".venv/", ".pytest_cache/",
        ):
            assert required in DEFAULT_IGNORE_PATTERNS, (
                f"missing default ignore: {required}"
            )
