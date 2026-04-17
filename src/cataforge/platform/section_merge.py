"""Section-level merge for instruction files (CLAUDE.md / AGENTS.md).

Deploy strategy ``update_strategy: section-merge`` preserves user modifications
across ``cataforge deploy`` runs. Each ``## `` heading is treated as an atomic
section, classified per the target's ``section_policy``:

- ``framework`` — framework-owned; body overwritten from new template.
- ``schema`` — template defines structure, user fills values; bullet-style
  ``- key: value`` fields are merged (user values preserved unless still a
  ``{placeholder}`` or listed in ``always_overwrite_fields``).
- ``runtime`` — orchestrator / bootstrap fills at runtime; body preserved from
  current file if non-empty, otherwise template default.
- _unlisted_ — if the current file has a section the template does not,
  it is preserved verbatim (user extension) when ``user_extensible`` is true.

``section_policy`` structure on a deploy target::

    section_policy:
      framework: [文档导航, 框架机制]
      schema: [项目信息, 全局约定]
      runtime: [项目状态, 执行环境]
      user_extensible: true
      always_overwrite_fields:       # per-section field overrides
        项目信息: [运行时]
"""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

_H2_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)
_FIELD_RE = re.compile(r"^- (?P<key>[^:\n]+?):\s*(?P<value>.*)$")
_PLACEHOLDER_RE = re.compile(r"^\{[^{}]*\}$")


def merge_sections(
    current: str,
    template: str,
    *,
    policy: dict[str, Any],
    platform_id: str = "",
) -> str:
    """Merge ``template`` into ``current`` per the supplied policy.

    The result preserves user-added sections, user-filled schema values, and
    runtime-populated content, while absorbing framework updates to
    framework-owned sections and newly introduced schema fields.
    """
    cur_preamble, cur_sections = _split(current)
    tpl_preamble, tpl_sections = _split(template)

    framework = set(policy.get("framework") or [])
    schema = set(policy.get("schema") or [])
    runtime = set(policy.get("runtime") or [])
    user_extensible = bool(policy.get("user_extensible", True))
    always_overwrite_fields_map: dict[str, set[str]] = {
        title: set(fields or [])
        for title, fields in (policy.get("always_overwrite_fields") or {}).items()
    }

    # Preamble handling: if the current preamble is semantically identical to
    # the template (ignoring whitespace differences) we treat it as "not
    # customized" and let the template win so framework upgrades propagate.
    # Otherwise the user has added banners / custom H1 / explanatory prose —
    # preserve it wholesale. This does mean a user who customizes preamble
    # won't receive future preamble-level framework updates automatically;
    # they must re-run deploy on a fresh preamble or reconcile by hand.
    result_preamble = _merge_preamble(cur_preamble, tpl_preamble)
    result: OrderedDict[str, str] = OrderedDict()

    # 1) Walk the template in its declared order so the framework can reorder.
    for title, tpl_body in tpl_sections.items():
        cur_body = cur_sections.get(title)
        category = _classify(title, framework, schema, runtime)
        if category == "framework":
            result[title] = tpl_body
        elif category == "schema":
            overwrite_fields = always_overwrite_fields_map.get(title, set())
            result[title] = (
                _merge_fields(cur_body, tpl_body, overwrite_fields=overwrite_fields)
                if cur_body is not None
                else tpl_body
            )
        elif category == "runtime":
            # Preserve what's already there; only use template when the section
            # is absent or is still the literal template body (first deploy).
            result[title] = (
                cur_body if cur_body is not None and cur_body.strip() else tpl_body
            )
        else:
            # Unclassified template section = framework-owned by default.
            result[title] = tpl_body

    # 2) Append user-added sections (present in current but not in template).
    if user_extensible:
        for title, body in cur_sections.items():
            if title not in result:
                result[title] = body

    return _serialize(result_preamble, result)


def _split(text: str) -> tuple[str, OrderedDict[str, str]]:
    """Split markdown into (preamble_before_first_h2, OrderedDict[title, body])."""
    matches = list(_H2_RE.finditer(text))
    if not matches:
        return text, OrderedDict()

    preamble = text[: matches[0].start()]
    sections: OrderedDict[str, str] = OrderedDict()
    for i, m in enumerate(matches):
        title = m.group("title").strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end]
        # Normalize leading newline so heading-to-body is consistent.
        if body.startswith("\n"):
            body = body[1:]
        sections[title] = body
    return preamble, sections


def _merge_preamble(cur: str, tpl: str) -> str:
    """Decide whether to keep user's preamble or use the template's.

    Preamble = everything before the first ``## `` heading. It typically holds
    an at-mention line (``@.cataforge/rules/COMMON-RULES.md``), the H1 title,
    and optionally user-added banner comments / explanatory prose.

    Policy:
    - If current is empty or whitespace-only → use template (first deploy).
    - If current and template are equal after whitespace normalization → use
      template so any framework-level preamble updates propagate.
    - Otherwise user has customized — preserve user's preamble entirely.
    """
    if not cur.strip():
        return tpl
    if _normalize_whitespace(cur) == _normalize_whitespace(tpl):
        return tpl
    return cur


def _normalize_whitespace(text: str) -> str:
    """Collapse consecutive whitespace to detect semantic equivalence."""
    return re.sub(r"\s+", " ", text).strip()


def _serialize(preamble: str, sections: OrderedDict[str, str]) -> str:
    """Rebuild the markdown preserving trailing-newline discipline."""
    out = [preamble]
    for title, body in sections.items():
        if out[-1] and not out[-1].endswith("\n"):
            out.append("\n")
        out.append(f"## {title}\n")
        out.append(body)
        if not body.endswith("\n"):
            out.append("\n")
    return "".join(out)


def _classify(
    title: str,
    framework: set[str],
    schema: set[str],
    runtime: set[str],
) -> str:
    stripped = _strip_section_annotations(title)
    for name, category in (
        (framework, "framework"),
        (schema, "schema"),
        (runtime, "runtime"),
    ):
        if title in name or stripped in name:
            return category
    return ""


def _strip_section_annotations(title: str) -> str:
    """Drop trailing parenthetical notes like '项目状态 (orchestrator专属写入区)'."""
    return re.sub(r"\s*\(.*?\)\s*$", "", title).strip()


def _merge_fields(
    cur_body: str,
    tpl_body: str,
    *,
    overwrite_fields: set[str],
) -> str:
    """Merge top-level ``- key: value`` bullets between current and template.

    - Template order drives the output order so framework upgrades can
      reorder/rename fields.
    - User values win when non-placeholder AND not listed in overwrite_fields.
    - User-added fields (present in current, absent from template) are
      appended after template fields to preserve customization.
    - Nested structure (multi-line bullet bodies) is preserved verbatim from
      whichever side owns the field in the output.
    """
    cur_parsed = _parse_bullets(cur_body)
    tpl_parsed = _parse_bullets(tpl_body)

    out_blocks: list[str] = []

    # Walk template order for known keys.
    for key, tpl_block in tpl_parsed.items():
        if key in overwrite_fields:
            out_blocks.append(tpl_block.text)
            continue
        cur_block = cur_parsed.get(key)
        if cur_block is None:
            out_blocks.append(tpl_block.text)
        elif _block_is_placeholder(cur_block):
            # User hasn't filled it in yet — absorb template's new default.
            out_blocks.append(tpl_block.text)
        else:
            out_blocks.append(cur_block.text)

    # Append user-added fields (in their original order).
    for key, cur_block in cur_parsed.items():
        if key not in tpl_parsed:
            out_blocks.append(cur_block.text)

    merged = "".join(out_blocks)

    # Preserve non-bullet tail content (trailing prose/comments) — take
    # whichever side has content. Prefer template so framework can update
    # boilerplate; fall back to current if template's tail is empty.
    tpl_tail = _extract_tail(tpl_body, tpl_parsed)
    cur_tail = _extract_tail(cur_body, cur_parsed)
    tail = tpl_tail if tpl_tail.strip() else cur_tail
    if tail and not merged.endswith("\n"):
        merged += "\n"
    return merged + tail


class _BulletBlock:
    __slots__ = ("key", "value", "text")

    def __init__(self, key: str, value: str, text: str) -> None:
        self.key = key
        self.value = value
        self.text = text


def _parse_bullets(body: str) -> OrderedDict[str, _BulletBlock]:
    """Parse top-level ``- key: value`` bullets from a section body.

    Continuation lines (indented with at least two spaces, or empty lines
    followed by further indentation) belong to the preceding bullet's block.
    HTML comments and lines before the first bullet form the *header* and are
    not attached to any key; they are returned via ``_extract_tail``.
    """
    lines = body.splitlines(keepends=True)
    blocks: OrderedDict[str, _BulletBlock] = OrderedDict()
    buf: list[str] = []
    cur_key: str | None = None
    cur_value: str = ""

    def flush() -> None:
        nonlocal buf, cur_key, cur_value
        if cur_key is not None:
            blocks[cur_key] = _BulletBlock(cur_key, cur_value, "".join(buf))
        buf = []
        cur_key = None
        cur_value = ""

    for line in lines:
        m = _FIELD_RE.match(line.rstrip("\r\n"))
        if m and not line.startswith(" ") and not line.startswith("\t"):
            # New top-level bullet
            flush()
            cur_key = m.group("key").strip()
            cur_value = m.group("value").strip()
            buf.append(line)
        else:
            if cur_key is not None:
                buf.append(line)
            # else: header / tail content, handled by _extract_tail

    flush()
    return blocks


def _extract_tail(
    body: str, parsed: OrderedDict[str, _BulletBlock]
) -> str:
    """Return content that is *not* part of any parsed bullet block."""
    if not parsed:
        return body
    # Simple path: if body starts with first bullet and consumed blocks cover
    # a contiguous region, the tail is whatever remains at the end.
    idx = body.find(next(iter(parsed.values())).text)
    if idx == -1:
        return ""
    header = body[:idx]
    # Find where the last bullet block ends.
    last_block = list(parsed.values())[-1]
    last_end = body.rfind(last_block.text) + len(last_block.text)
    tail = body[last_end:]
    # Only return header if it contains non-whitespace commentary (rare — most
    # schema sections start directly with bullets). Favor tail for now.
    if header.strip():
        return header + tail
    return tail


def _block_is_placeholder(block: _BulletBlock) -> bool:
    """Decide if a parsed bullet block is still at its template-placeholder state.

    A block has *content* if:
    - its inline value is non-empty and not a ``{placeholder}`` / em-dash, OR
    - it carries indented continuation lines with non-whitespace text
      (multi-line nested values like ``- 阶段配置:\\n  - ui_design: N/A``).

    If either condition holds, the user has filled it in and their version
    should be preserved over the template default.
    """
    # Inline value check
    if not _is_placeholder(block.value):
        return False
    # Continuation check: block.text is the full multi-line span; strip its
    # first line (where the "- key: value" lives) and see if any remaining
    # line has non-whitespace content.
    lines = block.text.split("\n", 1)
    if len(lines) < 2:
        return True
    continuation = lines[1]
    return not continuation.strip()


def _is_placeholder(value: str) -> bool:
    """Detect template placeholders: ``{...}`` or em-dash default ``—``."""
    stripped = value.strip()
    if not stripped:
        return True
    if _PLACEHOLDER_RE.match(stripped):
        return True
    return stripped == "—"
