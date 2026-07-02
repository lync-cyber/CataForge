"""code_check.py — code-review Layer 1 CLI.

用法:
  python -m cataforge.runtime.skill.builtins.code_review.code_check \
        review <file_or_dir> [--fix] [--focus <category[,...]>] [--format text|json]
  python -m cataforge.runtime.skill.builtins.code_review.code_check \
        scan <path> [--focus <category[,...]>] [--format text|json]

Exit codes follow COMMON-RULES §Layer 1 调用协议: 0=PASS,
1=fail-with-issues, 2=usage error / target missing. Unknown flags and
invalid ``--focus`` tokens are hard usage errors (exit 2), never silently
ignored.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cataforge.core.paths import project_root_from_env
from cataforge.runtime.skill.builtins.code_review.engine.findings import (
    render_json,
    render_text,
)
from cataforge.runtime.skill.builtins.code_review.engine.pipeline import (
    FocusError,
    execute,
)
from cataforge.utils.common import ensure_utf8

_DESCRIPTION = (
    "code-review Layer 1 用法: review <path> [--fix] [--focus <category[,...]>] | "
    "scan <path> [--focus <category[,...]>]；--format json 输出结构化 finding"
)


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="代码文件或目录")
    parser.add_argument(
        "--focus",
        default=None,
        help="逗号分隔的 category 列表（COMMON-RULES §统一问题分类体系）",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text", dest="fmt")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="code-review", description=_DESCRIPTION)
    sub = parser.add_subparsers(dest="mode", required=True)
    review = sub.add_parser("review", help="任务粒度评审（lint + wiring + ui-fidelity）")
    review.add_argument("--fix", action="store_true", help="以修复模式运行外部工具")
    _add_common(review)
    scan = sub.add_parser("scan", help="项目级健康度扫描（lint 门禁 + 腐化 probe）")
    _add_common(scan)
    return parser


def run(
    mode: str,
    target: str,
    *,
    fix: bool = False,
    focus: list[str] | None = None,
    fmt: str = "text",
) -> int:
    """Core entry: run the pipeline and print the rendered result."""
    target_path = Path(target)
    if not target_path.exists():
        print(f"ERROR: 目标路径不存在: {target_path}")
        return 2
    try:
        result = execute(
            mode,
            target_path,
            fix=fix,
            focus=focus,
            project_root=project_root_from_env(),
        )
    except FocusError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(render_json(result) if fmt == "json" else render_text(result))
    return result.exit_code


def main() -> None:
    ensure_utf8()
    args = build_parser().parse_args()
    focus = [c.strip() for c in args.focus.split(",") if c.strip()] if args.focus else None
    sys.exit(
        run(
            args.mode,
            args.target,
            fix=getattr(args, "fix", False),
            focus=focus,
            fmt=args.fmt,
        )
    )


if __name__ == "__main__":
    main()
