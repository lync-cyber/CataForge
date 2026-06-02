"""Path normalization — .cataforge detection in lint_format."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LINT_FORMAT_SCRIPT = (
    REPO_ROOT / "src" / "cataforge" / "runtime" / "hook" / "scripts" / "lint_format.py"
)


def _run(script: Path, payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=60,
        check=False,
    )


class TestLintFormatPathNormalization:
    def test_unix_style_cataforge_path_skips_markdownlint(self, tmp_path: Path) -> None:
        md = tmp_path / ".cataforge" / "skills" / "foo.md"
        md.parent.mkdir(parents=True)
        md.write_text("# Hello\n", encoding="utf-8")
        result = _run(
            LINT_FORMAT_SCRIPT,
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(md).replace("\\", "/")},
            },
        )
        assert result.returncode == 0

    def test_windows_style_cataforge_path_skips_markdownlint(self, tmp_path: Path) -> None:
        md = tmp_path / ".cataforge" / "skills" / "foo.md"
        md.parent.mkdir(parents=True)
        md.write_text("# Hello\n", encoding="utf-8")
        result = _run(
            LINT_FORMAT_SCRIPT,
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(md).replace("/", "\\")},
            },
        )
        assert result.returncode == 0

    def test_relative_cataforge_path_skips_markdownlint(self, tmp_path: Path) -> None:
        md = tmp_path / ".cataforge" / "skills" / "foo.md"
        md.parent.mkdir(parents=True)
        md.write_text("# Hello\n", encoding="utf-8")
        result = _run(
            LINT_FORMAT_SCRIPT,
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": ".cataforge/skills/foo.md"},
            },
        )
        assert result.returncode == 0
