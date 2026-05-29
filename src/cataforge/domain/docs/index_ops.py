"""Shared docs index primitives — leaf module with no kg/loader/indexer deps.

Houses the ref-resolution exception hierarchy, the doc_id->doc_type map, and
the index lookup helpers consumed by *both* ``loader`` and ``indexer`` (and
the doc_type map by ``kg`` ingest/reconcile). Keeping these here breaks the
old docs<->kg import cycle and the indexer->loader private-symbol crossing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_DOC_TYPE_MAP: dict[str, str] = {
    "prd": "prd",
    "arch": "arch",
    "ui-spec": "ui-spec",
    "dev-plan": "dev-plan",
    "test-report": "test-report",
    # `test` is the canonical KG-cutover alias for the test-report subdir
    # (matches `KGConfig.kg_active_doc_types` default `{prd, arch, test}`
    # and `cataforge.interface.cli.doctor.kg_ingestion._doc_type_to_subdir`).
    "test": "test-report",
    "deploy-spec": "deploy-spec",
    "research": "research",
    "changelog": "changelog",
    "brief": "brief",
}


_DOC_TYPE_MAP_CACHE: dict[str, dict[str, str]] = {}


def _load_doc_type_map(project_root: str) -> dict[str, str]:
    """Resolve the doc_id → doc_type map for ``project_root``.

    Lookup order:
        1. ``.cataforge/framework.json`` ``docs.doc_types`` (merged on top of defaults)
        2. Built-in defaults (when framework.json is missing or has no override)
    """
    cached = _DOC_TYPE_MAP_CACHE.get(project_root)
    if cached is not None:
        return cached

    from cataforge.core.paths import ProjectPaths

    merged = dict(DEFAULT_DOC_TYPE_MAP)
    framework_json = ProjectPaths(Path(project_root)).framework_json
    if framework_json.is_file():
        try:
            with open(framework_json, encoding="utf-8") as f:
                data = json.load(f)
            override = (data.get("docs") or {}).get("doc_types")
            if isinstance(override, dict):
                for k, v in override.items():
                    if isinstance(k, str) and isinstance(v, str):
                        merged[k] = v
        except (json.JSONDecodeError, OSError):
            pass

    _DOC_TYPE_MAP_CACHE[project_root] = merged
    return merged


def _get_doc_type_map(project_root: str | None = None) -> dict[str, str]:
    if project_root is None:
        return dict(DEFAULT_DOC_TYPE_MAP)
    return _load_doc_type_map(project_root)


def _resolve_doc_entry(index: dict[str, Any], doc_id: str) -> dict[str, Any] | None:
    """Resolve ``doc_id`` to a document entry via the staged lookup chain.

    Order: exact match → aliases map → prefix fallback (``{doc_id}-*``).
    The prefix stage collects all candidates and raises
    :class:`AmbiguousRefError` when more than one matches — silently picking
    the first dict-iteration hit was the pre-fix behavior and produced
    nondeterministic resolution when projects had ``prd-v1`` and ``prd-v2``
    side by side.
    """
    documents = index.get("documents", {})
    direct = documents.get(doc_id)
    if direct:
        return direct

    aliases = index.get("aliases") or {}
    target = aliases.get(doc_id)
    if isinstance(target, str):
        aliased = documents.get(target)
        if aliased:
            return aliased

    prefix = doc_id + "-"
    candidates = [(did, d) for did, d in documents.items() if did.startswith(prefix)]
    if len(candidates) == 1:
        return candidates[0][1]
    if len(candidates) > 1:
        names = ", ".join(sorted(did for did, _ in candidates))
        raise AmbiguousRefError(
            f"短引用 {doc_id!r} 匹配到多个文档: {names}。请使用完整 doc_id "
            f"或在源文档 frontmatter 中声明 `aliases:`。"
        )
    return None


def _lookup_in_index(
    index: dict[str, Any], doc_id: str, section_path: str, item_id: str | None
) -> dict[str, Any] | None:
    doc_entry = _resolve_doc_entry(index, doc_id)
    if not doc_entry:
        return None

    sections = doc_entry.get("sections", {})
    top_sec = section_path.split(".")[0] if "." in section_path else section_path
    sec_data = sections.get(top_sec)
    if not sec_data:
        return None

    file_path = doc_entry["file_path"]

    if item_id:
        item_data = sec_data.get("items", {}).get(item_id)
        if item_data:
            return {
                "file_path": file_path,
                "line_start": item_data["line_start"],
                "line_end": item_data["line_end"],
                "est_tokens": item_data.get("est_tokens", 0),
                "deps": item_data.get("deps", []),
            }
        xref = index.get("xref", {})
        if item_id in xref:
            for ref_entry in xref[item_id]:
                try:
                    other_doc = _resolve_doc_entry(index, ref_entry["doc_id"])
                except AmbiguousRefError:
                    other_doc = None
                if other_doc:
                    other_sec = other_doc.get("sections", {}).get(ref_entry["section"], {})
                    other_item = other_sec.get("items", {}).get(item_id)
                    if other_item:
                        return {
                            "file_path": ref_entry["file_path"],
                            "line_start": other_item["line_start"],
                            "line_end": other_item["line_end"],
                            "est_tokens": other_item.get("est_tokens", 0),
                            "deps": other_item.get("deps", []),
                        }
        return None

    if "." in section_path:
        sub_data = sec_data.get("items", {}).get(section_path)
        if sub_data:
            return {
                "file_path": file_path,
                "line_start": sub_data["line_start"],
                "line_end": sub_data["line_end"],
                "est_tokens": sub_data.get("est_tokens", 0),
                "deps": sub_data.get("deps", []),
            }
        return None

    return {
        "file_path": file_path,
        "line_start": sec_data["line_start"],
        "line_end": sec_data["line_end"],
        "est_tokens": sec_data.get("est_tokens", 0),
        "deps": sec_data.get("deps", []),
    }


class LoadSectionError(Exception):
    pass


class RefParseError(LoadSectionError):
    pass


class DocResolveError(LoadSectionError):
    pass


class SectionNotFoundError(LoadSectionError):
    pass


class AmbiguousRefError(LoadSectionError):
    pass
