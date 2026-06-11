"""Reader helpers for ``framework.json`` and ``docs/EVENT-LOG.jsonl``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cataforge.core.config import ConfigManager
from cataforge.core.event_log import EVENT_LOG_REL

from ._constants import DEFAULT_EVENT_LOG_DRIFT_MIN_EVENTS


def read_framework_data(root: Path) -> dict[str, Any]:
    """Return parsed ``framework.json`` content, or empty dict on failure."""
    try:
        data = ConfigManager(root).load_raw()
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def is_editable_tree(root: Path) -> bool:
    """True iff *root* is a CataForge source checkout (editable install).

    The proxy is ``src/cataforge/`` existing as a package dir — present in
    the dogfood / editable tree, absent in a downstream site-packages
    install. Gates checks that only make sense against framework source
    (e.g. a migration check's ``src/`` path must resolve here but legitimately
    does not downstream).
    """
    return (root / "src" / "cataforge").is_dir()


# (constant_name, regex_template, hint_template) — ``__V__`` is replaced with
# the live framework.json value so B4 flags whatever number the constant
# currently holds instead of a hardcoded copy that silently goes stale.
_CONSTANT_LITERAL_TEMPLATES: tuple[tuple[str, str, str], ...] = (
    ("MAX_QUESTIONS_PER_BATCH", r"≤\s*__V__\s*(问|题|个问题)", "≤__V__ 问"),
    ("DOC_SPLIT_THRESHOLD_LINES", r"(>|超过|≥)\s*__V__\s*行", ">__V__ 行"),
    ("DOC_REVIEW_L2_SKIP_THRESHOLD_LINES", r"<\s*__V__\s*行", "<__V__ 行"),
    ("TDD_LIGHT_LOC_THRESHOLD", r"(≤|<|>)\s*__V__\s*(LOC|loc|行代码)", "__V__ LOC 阈值"),
    ("RETRO_TRIGGER_SELF_CAUSED", r"(累计|≥)\s*__V__\s*条", "≥__V__ 条"),
    ("SPRINT_REVIEW_MICRO_TASK_COUNT", r"(≤|<=)\s*__V__\s*个任务", "≤__V__ 个任务"),
)


def build_constant_literals(root: Path) -> tuple[tuple[str, str, str], ...]:
    """Build B4's ``(name, regex, hint)`` triples with values read live from
    framework.json. A constant absent or non-integer is skipped (no literal
    to match against)."""
    consts = read_framework_data(root).get("constants") or {}
    if not isinstance(consts, dict):
        return ()
    out: list[tuple[str, str, str]] = []
    for name, pattern_t, hint_t in _CONSTANT_LITERAL_TEMPLATES:
        value = consts.get(name)
        if not isinstance(value, int):
            continue
        v = str(value)
        out.append((name, pattern_t.replace("__V__", v), hint_t.replace("__V__", v)))
    return tuple(out)


def read_framework_features(root: Path) -> dict[str, dict[str, object]]:
    """Return ``framework.json#/features`` mapping, or empty on failure."""
    data = read_framework_data(root)
    features = data.get("features")
    if not isinstance(features, dict):
        return {}
    return {str(k): v for k, v in features.items() if isinstance(v, dict)}


def read_dispatcher_skills(root: Path) -> set[str]:
    """Return the set of skill ids that act as agent dispatchers.

    Declared at the top level of ``framework.json`` under
    ``dispatcher_skills``.  These skills appear in orchestrator's Phase
    Routing table as the agent name (e.g. ``Phase 5 development → tdd-engine``)
    even though they're skills, not agents — without this declaration B5 has
    no way to distinguish "phase routes to skill" from "phase routes to
    nonexistent agent".
    """
    data = read_framework_data(root)
    raw = data.get("dispatcher_skills") or []
    if not isinstance(raw, list):
        return set()
    return {str(x) for x in raw if isinstance(x, str)}


def read_event_log_threshold(root: Path) -> int:
    """Return ``constants.EVENT_LOG_DRIFT_MIN_EVENTS`` from framework.json."""
    data = read_framework_data(root)
    consts = data.get("constants") or {}
    if isinstance(consts, dict):
        v = consts.get("EVENT_LOG_DRIFT_MIN_EVENTS")
        if isinstance(v, int) and v >= 0:
            return v
    return DEFAULT_EVENT_LOG_DRIFT_MIN_EVENTS


def read_anti_pattern_floor(root: Path, kind: str) -> int:
    """Return ``constants.ANTI_PATTERN_MIN_COUNT_<KIND>`` from framework.json.

    kind ∈ {"SKILL", "AGENT"}.  Defaults: 3 for SKILL, 4 for AGENT.
    """
    data = read_framework_data(root)
    consts = data.get("constants") or {}
    key = f"ANTI_PATTERN_MIN_COUNT_{kind}"
    fallback = 3 if kind == "SKILL" else 4
    if isinstance(consts, dict):
        v = consts.get(key)
        if isinstance(v, int) and v >= 0:
            return v
    return fallback


def agent_model_defaults(root: Path) -> dict[str, str]:
    """Return ``constants.AGENT_MODEL_DEFAULTS`` from framework.json."""
    data = read_framework_data(root)
    consts = data.get("constants") or {}
    if not isinstance(consts, dict):
        return {}
    raw = consts.get("AGENT_MODEL_DEFAULTS") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if isinstance(v, str)}


def heavy_whitelist(root: Path) -> set[str]:
    """Return ``constants.AGENT_MODEL_TIER_HEAVY_WHITELIST`` from framework.json."""
    data = read_framework_data(root)
    consts = data.get("constants") or {}
    if not isinstance(consts, dict):
        return set()
    raw = consts.get("AGENT_MODEL_TIER_HEAVY_WHITELIST") or []
    if not isinstance(raw, list):
        return set()
    return {str(x) for x in raw if isinstance(x, str)}


def read_event_log_returns(
    root: Path,
) -> tuple[dict[str, int], dict[str, int]]:
    """Return ``({agent: return_count}, {agent: returns_with_ref})``.

    Reads ``docs/EVENT-LOG.jsonl`` line-by-line. Tolerates malformed lines
    (skipped silently) since the log is append-only and may have partial
    writes from crashed processes. Returns empty dicts if the file is
    missing — caller treats that as "no event data, skip cross-check"
    rather than treating absence as evidence of dead routing.
    """
    log_path = root / EVENT_LOG_REL
    if not log_path.is_file():
        return {}, {}

    returns: dict[str, int] = {}
    returns_with_ref: dict[str, int] = {}
    try:
        with log_path.open(errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                if record.get("event") != "agent_return":
                    continue
                agent = record.get("agent")
                if not isinstance(agent, str) or not agent:
                    continue
                returns[agent] = returns.get(agent, 0) + 1
                ref = record.get("ref")
                if isinstance(ref, str) and ref:
                    returns_with_ref[agent] = returns_with_ref.get(agent, 0) + 1
    except OSError:
        pass
    return returns, returns_with_ref
