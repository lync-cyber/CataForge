"""模板 Override 渲染引擎。

实现 D-2 的继承覆盖策略:
1. 读取基础模板（含 OVERRIDE 标记）
2. 读取平台 override 文件（如果存在）
3. 用 override 段落替换基础模板中的对应段落
"""
from __future__ import annotations
import re
from pathlib import Path

_CATAFORGE_DIR = Path(__file__).resolve().parent.parent

_OVERRIDE_PATTERN = re.compile(
    r"<!-- OVERRIDE:(\w+) -->\n(.*?)<!-- /OVERRIDE:\1 -->",
    re.DOTALL,
)


def render_template(
    template_rel_path: str,
    platform_id: str,
) -> str:
    """渲染模板：base + platform override。

    Args:
        template_rel_path: 相对于 .cataforge/ 的模板路径
        platform_id: 平台标识

    Returns:
        合并后的模板文本。
    """
    base_path = _CATAFORGE_DIR / template_rel_path
    base_content = base_path.read_text(encoding="utf-8")

    override_path = (
        _CATAFORGE_DIR / "platforms" / platform_id / "overrides"
        / Path(template_rel_path).name
    )

    if not override_path.is_file():
        return _strip_override_markers(base_content)

    override_content = override_path.read_text(encoding="utf-8")
    overrides = _parse_overrides(override_content)

    def replacer(match: re.Match) -> str:
        name = match.group(1)
        if name in overrides:
            return overrides[name]
        return match.group(2)

    merged = _OVERRIDE_PATTERN.sub(replacer, base_content)
    return merged


def list_override_points(template_rel_path: str) -> list[str]:
    """列出模板中所有 OVERRIDE 标记点名。"""
    base_path = _CATAFORGE_DIR / template_rel_path
    content = base_path.read_text(encoding="utf-8")
    return [m.group(1) for m in _OVERRIDE_PATTERN.finditer(content)]


def _parse_overrides(content: str) -> dict[str, str]:
    """从 override 文件中提取各段落内容。"""
    return {m.group(1): m.group(2) for m in _OVERRIDE_PATTERN.finditer(content)}


def _strip_override_markers(content: str) -> str:
    """移除 OVERRIDE 标记，保留默认内容。"""
    return _OVERRIDE_PATTERN.sub(r"\2", content)
