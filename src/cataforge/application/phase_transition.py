"""Phase Transition Protocol's deterministic gate chain as one idempotent run.

The orchestrator's Phase Transition Protocol mixes LLM-side state persistence
(doc/instruction-file status updates) with a fixed chain of CLI gates. This
module codifies the deterministic chain — phase-field sanity, doc-status
consistency check, dependency freshness, backend reconcile, cross-document
consistency, the 4-record transition event batch, and instruction-file
hygiene — behind ``cataforge phase transition`` (thin CLI in
:mod:`cataforge.interface.cli.phase_cmd`).

Contract: gates run in protocol order and the chain halts at the first gate
that needs a human/LLM decision, reporting structured options; a re-run after
the decision is safe. Decision/telemetry audit records (acks, degrade notes,
reconcile skips, compact) are appended the moment they are earned — deduped by
exact (event, phase, detail) content so re-runs don't duplicate them — which
means a later gate stop can never lose them. The 4-record transition batch is
skipped only when the log's newest ``phase_start`` already names the target
phase AND no phase-flow event (phase_start / phase_end / revision_start /
incident) for the source phase follows it, so a rollback-then-retransition
still logs its own batch. Decisions are carried back in as flags
(``ack_stale_deps``, ``ack_inconsistency``, ``compact``).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cataforge.adapter.platform.registry import (
    parse_current_phase,
    read_execution_mode,
    resolve_instruction_file,
)
from cataforge.application.phase import _find_phase_doc, parse_doc_status
from cataforge.core.claude_md_hygiene import (
    compact_learnings_registry,
    limit_breaches,
    measure_claude_md,
)
from cataforge.core.config import ConfigManager
from cataforge.core.errors import CataforgeError
from cataforge.core.event_log import EventLogError, append_batch, append_event, build_record
from cataforge.core.phases import PHASE_DOC_TYPE, PHASES
from cataforge.domain.docs.indexer import INDEX_FILENAME, validate_docs
from cataforge.domain.kg._dispatch import kg_enabled
from cataforge.utils.frontmatter import split_yaml_frontmatter

# Gate outcomes:
# pass — gate evaluated and satisfied; warn — satisfied with a caveat worth
# reading; skip — not applicable this run; stop — needs a decision, chain
# halted (exit 3); fail — broken tooling/environment, chain halted (exit 1).
OUTCOME_PASS = "pass"
OUTCOME_WARN = "warn"
OUTCOME_SKIP = "skip"
OUTCOME_STOP = "stop"
OUTCOME_FAIL = "fail"

# approved / approved_with_notes, optionally followed by a whitespace- or
# parenthesis-separated annotation ("approved (2026-07-01)"); rejects
# arbitrary suffix strings like "approvedX".
_APPROVED_RE = re.compile(r"approved(_with_notes)?([\s(（].*)?\Z", re.DOTALL)
_MIN_DOCS_FOR_CONSISTENCY = 2
_DOC_CONSISTENCY_SKILL = "doc-consistency"

# Events that mark the workflow's position moving between phases. Used by the
# batch dedup check: a record of one of these kinds for the source phase
# *after* the newest ``phase_start`` of the target phase means the workflow
# went back (revision / rollback), so the next transition is a new one — not
# an idempotent re-run. Audit ``state_change`` records deliberately don't
# count: they carry the source phase but don't move the workflow.
_FLOW_EVENTS = frozenset({"phase_start", "phase_end", "revision_start", "incident"})


def _is_approved(status: str | None) -> bool:
    return bool(status) and _APPROVED_RE.fullmatch(str(status).strip()) is not None


@dataclass(frozen=True)
class GateOption:
    """One structured choice offered when a gate stops the chain."""

    label: str
    action: str

    def to_dict(self) -> dict[str, str]:
        return {"label": self.label, "action": self.action}


@dataclass
class GateResult:
    """Outcome of a single deterministic gate."""

    gate: str
    outcome: str
    detail: str
    options: list[GateOption] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "outcome": self.outcome,
            "detail": self.detail,
            "options": [o.to_dict() for o in self.options],
        }


@dataclass
class TransitionReport:
    """Full result of one ``run_transition`` pass."""

    from_phase: str
    to_phase: str
    gates: list[GateResult] = field(default_factory=list)
    dispatch: dict[str, str] | None = None

    @property
    def stopped_at(self) -> GateResult | None:
        return next(
            (g for g in self.gates if g.outcome in (OUTCOME_STOP, OUTCOME_FAIL)),
            None,
        )

    @property
    def ok(self) -> bool:
        return self.stopped_at is None

    def to_dict(self) -> dict[str, Any]:
        stopped = self.stopped_at
        return {
            "from_phase": self.from_phase,
            "to_phase": self.to_phase,
            "ok": self.ok,
            "gates": [g.to_dict() for g in self.gates],
            "stopped_at": stopped.gate if stopped else None,
            "dispatch": self.dispatch,
        }


def run_transition(
    root: Path,
    *,
    from_phase: str,
    to_phase: str,
    ack_stale_deps: bool = False,
    ack_inconsistency: bool = False,
    compact: bool = False,
) -> TransitionReport:
    """Run the transition gate chain for ``from_phase → to_phase``.

    Raises :class:`CataforgeError` on unusable input (unknown phase, missing
    instruction file); gate verdicts — including tooling failures inside a
    gate — are reported in the returned :class:`TransitionReport` instead so
    the caller sees the whole chain state.
    """
    _validate_phases(from_phase, to_phase)
    instruction_file = resolve_instruction_file(root)
    if not instruction_file.is_file():
        raise CataforgeError(
            f"no {instruction_file.name} at {root} — not a driven CataForge project."
        )
    state_text = instruction_file.read_text(errors="replace")

    report = TransitionReport(from_phase=from_phase, to_phase=to_phase)
    steps: tuple[Callable[[], GateResult], ...] = (
        lambda: _gate_phase_field(state_text, from_phase, to_phase),
        lambda: _gate_doc_status(root, state_text, from_phase),
        lambda: _gate_stale_deps(root, from_phase, ack_stale_deps),
        lambda: _gate_reconcile(root, from_phase),
        lambda: _gate_doc_consistency(root, state_text, from_phase, ack_inconsistency),
        lambda: _gate_event_batch(root, instruction_file.name, from_phase, to_phase),
        lambda: _gate_claude_md(root, instruction_file, to_phase, compact),
    )
    for step in steps:
        result = step()
        report.gates.append(result)
        if result.outcome in (OUTCOME_STOP, OUTCOME_FAIL):
            return report

    report.dispatch = _dispatch_hint(root, to_phase)
    return report


# ─── gate implementations ────────────────────────────────────────────────────


def _validate_phases(from_phase: str, to_phase: str) -> None:
    for label, value in (("--from", from_phase), ("--to", to_phase)):
        if value not in PHASES:
            raise CataforgeError(
                f"{label} {value!r} is not a recognised phase; expected one of: "
                + ", ".join(PHASES)
            )
    if from_phase == to_phase:
        raise CataforgeError("--from and --to must differ (a transition changes phase).")
    if from_phase == "completed":
        raise CataforgeError("--from 'completed' is terminal — nothing to transition out of.")


def _gate_phase_field(state_text: str, from_phase: str, to_phase: str) -> GateResult:
    """Sanity-check 当前阶段 against the transition arguments.

    During the protocol the LLM may already have advanced the instruction
    file's 当前阶段 to the target phase, so either value is expected; anything
    else means the wrong transition is being driven — proceeding would append
    an out-of-order event batch, so this stops instead of warning.
    """
    gate = "phase-field"
    current = parse_current_phase(state_text)
    if not current:
        return GateResult(gate, OUTCOME_SKIP, "instruction file has no 当前阶段 line")
    if current in (from_phase, to_phase):
        return GateResult(gate, OUTCOME_PASS, f"当前阶段 = {current!r} matches the transition")
    return GateResult(
        gate,
        OUTCOME_STOP,
        f"instruction file 当前阶段 is {current!r}, which matches neither "
        f"--from {from_phase!r} nor --to {to_phase!r} — wrong transition being driven?",
        options=[
            GateOption(
                "核对参数后重跑",
                "确认 --from/--to 是否为当前应执行的转换；"
                "若 Step 1 尚未更新 当前阶段，先补齐再重跑",
            ),
            GateOption("暂停", "等待人工处理"),
        ],
    )


def _doc_status_for(doc_status: dict[str, str], doc_type: str) -> str | None:
    """文档状态 value for a doc_type, accepting the ``-lite`` variant key."""
    return doc_status.get(doc_type) or doc_status.get(f"{doc_type}-lite")


def _gate_doc_status(root: Path, state_text: str, from_phase: str) -> GateResult:
    """Verify the closing phase's doc(s) are approved on both sides.

    Covers the protocol's LLM-side persistence steps read-only: the doc's
    frontmatter ``status`` and the instruction file's 文档状态 field must both
    read approved before the deterministic gates may run.
    """
    gate = "doc-status"
    doc_types = PHASE_DOC_TYPE.get(from_phase)
    if doc_types is None:
        return GateResult(gate, OUTCOME_SKIP, f"phase {from_phase!r} carries no document gate")
    if isinstance(doc_types, str):
        doc_types = (doc_types,)

    doc_status = parse_doc_status(state_text)
    problems: list[str] = []
    for doc_type in doc_types:
        field_status = _doc_status_for(doc_status, doc_type)
        if not _is_approved(field_status):
            problems.append(f"文档状态.{doc_type} = {field_status or '未开始'} (expected approved)")

        doc_path = _find_phase_doc(root / "docs", doc_type)
        if doc_path is None:
            problems.append(f"{doc_type}: no document found under docs/")
            continue
        fm, _ = split_yaml_frontmatter(doc_path.read_text(errors="replace"))
        fm_status = str((fm or {}).get("status") or "")
        if not _is_approved(fm_status):
            problems.append(
                f"{doc_path.relative_to(root).as_posix()}: frontmatter status = "
                f"{fm_status or '(absent)'} (expected approved)"
            )

    if not problems:
        return GateResult(
            gate, OUTCOME_PASS, f"{', '.join(doc_types)}: doc + 文档状态 both approved"
        )
    return GateResult(
        gate,
        OUTCOME_STOP,
        "; ".join(problems),
        options=[
            GateOption(
                "完成状态持久化后重跑",
                "把文档头 status 与 {INSTRUCTION_FILE} 文档状态更新为 approved，再重跑本命令",
            ),
            GateOption("暂停", "等待人工处理"),
        ],
    )


def _gate_stale_deps(root: Path, from_phase: str, ack_stale_deps: bool) -> GateResult:
    """Dependency freshness: block on stale upstream deps unless acknowledged."""
    gate = "stale-deps"
    if not (root / "docs" / INDEX_FILENAME).is_file():
        return GateResult(
            gate,
            OUTCOME_STOP,
            f"docs/{INDEX_FILENAME} not found — the freshness gate needs the docs index",
            options=[
                GateOption("重建索引后重跑", "运行 `cataforge context index` 后重跑本命令"),
                GateOption("暂停", "等待人工处理"),
            ],
        )

    result = validate_docs(str(root))
    integrity = {
        key: len(result.get(key) or [])
        for key in ("orphans", "stale", "xref_errors", "alias_conflicts", "invalid_ids")
    }
    broken = {k: v for k, v in integrity.items() if v}
    if broken:
        summary = ", ".join(f"{v} {k}" for k, v in broken.items())
        return GateResult(
            gate,
            OUTCOME_STOP,
            f"docs index integrity failed ({summary}) — fix before transitioning",
            options=[
                GateOption(
                    "修复索引问题后重跑", "运行 `cataforge context validate` 查看明细并修复"
                ),
                GateOption("暂停", "等待人工处理"),
            ],
        )

    stale_deps = list(result.get("stale_deps") or [])
    if not stale_deps:
        return GateResult(gate, OUTCOME_PASS, "0 stale dep(s)")

    pairs = ", ".join(f"{sd['doc_id']}←{sd['upstream_id']}" for sd in stale_deps)
    if ack_stale_deps:
        upstream_ids = ", ".join(sorted({sd["upstream_id"] for sd in stale_deps}))
        note = _log_audit_once(
            root,
            event="state_change",
            phase=from_phase,
            detail=f"stale deps acknowledged: {upstream_ids}",
        )
        return GateResult(
            gate,
            OUTCOME_WARN,
            f"{len(stale_deps)} stale dep(s) acknowledged, degraded to WARN ({note}): {pairs}",
        )
    return GateResult(
        gate,
        OUTCOME_STOP,
        f"{len(stale_deps)} stale dep(s) — upstream changed after downstream was written: {pairs}",
        options=[
            GateOption("cascade_amendment", "进入 cascade_amendment 更新受影响文档"),
            GateOption("确认不影响下游", "重跑本命令并加 --ack-stale-deps（决策即时记 EVENT-LOG）"),
            GateOption("暂停", "手动审查"),
        ],
    )


def _gate_reconcile(root: Path, from_phase: str) -> GateResult:
    """Backend drift guard; skips (with an audit note) when it cannot run."""
    gate = "reconcile"
    if not kg_enabled(root):
        return GateResult(
            gate, OUTCOME_SKIP, "markdown mode — no graph backend, reconcile is a no-op"
        )

    from cataforge.application.context.write import reconcile_check  # noqa: PLC0415

    try:
        result = reconcile_check(str(root))
    except Exception as exc:  # store missing / corrupt etc. — WARN, don't block
        note = _log_audit_once(
            root,
            event="state_change",
            phase=from_phase,
            detail=f"reconcile skipped at phase transition: {type(exc).__name__}: {exc}",
        )
        return GateResult(gate, OUTCOME_WARN, f"reconcile skipped ({exc}) — {note}")

    if result.ok:
        return GateResult(gate, OUTCOME_PASS, "no drift")

    # ReconcileReport carries per-document remediation records; the markdown-
    # backend DocValidationReport does not (its integrity issues already gate
    # at stale-deps), so an empty list is the correct degenerate summary.
    remediations = [
        f"{d.source_path} → {d.remediation} ({d.state})"
        for d in getattr(result, "documents", [])
        if d.state != "in_sync" or d.desynced_sections
    ]
    detail = f"DRIFT: {result.gate_summary}"
    if remediations:
        detail += " · remediation: " + "; ".join(remediations)
    return GateResult(
        gate,
        OUTCOME_STOP,
        detail,
        options=[
            GateOption(
                "按 remediation 修复后重跑",
                "export → `cataforge context finalize` 重导出；ingest → 先归因"
                "（Agent 绕写则回滚重走 authoring，确认人改导出文件才 "
                "`cataforge context ingest` 回灌）；manual → 人工处理；修复后重跑本命令",
            ),
            GateOption("cascade_amendment", "修订上游文档以匹配图谱"),
            GateOption("暂停", "手动审查"),
        ],
    )


def _count_approved_docs(state_text: str) -> int:
    return sum(1 for status in parse_doc_status(state_text).values() if _is_approved(status))


def _gate_doc_consistency(
    root: Path,
    state_text: str,
    from_phase: str,
    ack_inconsistency: bool,
) -> GateResult:
    """Cross-document consistency via the doc-consistency Layer 1 skill."""
    gate = "doc-consistency"
    approved = _count_approved_docs(state_text)
    if approved < _MIN_DOCS_FOR_CONSISTENCY:
        return GateResult(
            gate,
            OUTCOME_SKIP,
            f"only {approved} approved doc(s) — cross-doc check needs ≥{_MIN_DOCS_FOR_CONSISTENCY}",
        )

    from cataforge.runtime.skill.runner import SkillRunner, SkillTimeoutError  # noqa: PLC0415

    try:
        runner = SkillRunner(project_root=root)
        proc = runner.run(
            _DOC_CONSISTENCY_SKILL, ["docs/", "--format", "json"], agent="orchestrator"
        )
    except (ValueError, FileNotFoundError) as exc:
        return GateResult(gate, OUTCOME_WARN, f"doc-consistency unavailable ({exc}) — skipped")
    except SkillTimeoutError as exc:
        return GateResult(gate, OUTCOME_FAIL, f"doc-consistency timed out: {exc}")

    severities = _issue_severities(proc.stdout)
    if proc.returncode == 0:
        non_blocking = {k: v for k, v in severities.items() if k in ("MEDIUM", "LOW") and v}
        if non_blocking:
            summary = ", ".join(f"{v} {k}" for k, v in sorted(non_blocking.items()))
            note = _log_audit_once(
                root,
                event="state_change",
                phase=from_phase,
                detail=f"doc-consistency WARN at phase transition: {summary}",
            )
            return GateResult(gate, OUTCOME_WARN, f"consistent with findings ({note}): {summary}")
        return GateResult(gate, OUTCOME_PASS, "consistent")

    if proc.returncode == 1:
        blocking = {k: v for k, v in severities.items() if k in ("CRITICAL", "HIGH") and v}
        summary = ", ".join(f"{v} {k}" for k, v in sorted(blocking.items())) or "blocking findings"
        if ack_inconsistency:
            note = _log_audit_once(
                root,
                event="state_change",
                phase=from_phase,
                detail=f"doc-consistency inconsistency degraded to WARN: {summary}",
            )
            return GateResult(
                gate, OUTCOME_WARN, f"inconsistent, degraded to WARN ({note}): {summary}"
            )
        return GateResult(
            gate,
            OUTCOME_STOP,
            f"inconsistent: {summary}",
            options=[
                GateOption("cascade_amendment", "修复跨文档不一致"),
                GateOption(
                    "降级为 WARN 继续", "重跑本命令并加 --ack-inconsistency（决策即时记 EVENT-LOG）"
                ),
                GateOption("暂停", "手动审查"),
            ],
        )

    # exit 2 / 127 class: broken invocation or environment — Layer 1 FAIL.
    return GateResult(
        gate,
        OUTCOME_FAIL,
        f"doc-consistency exited {proc.returncode} (bad arguments / not executable) — "
        "run `cataforge doctor` first",
    )


def _issue_severities(stdout: str) -> dict[str, int]:
    """Severity → count from a doc-consistency ``--format json`` report."""
    try:
        data = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return {}
    counts: dict[str, int] = {}
    issues = data.get("issues")
    if not isinstance(issues, list):
        return counts
    for issue in issues:
        if isinstance(issue, dict):
            sev = str(issue.get("severity", "")).upper()
            if sev:
                counts[sev] = counts.get(sev, 0) + 1
    return counts


# ─── event-log plumbing ──────────────────────────────────────────────────────


def _read_log_records(root: Path) -> list[dict[str, Any]]:
    """Tolerantly parse EVENT-LOG.jsonl; bad/truncated lines are skipped."""
    log = root / "docs" / "EVENT-LOG.jsonl"
    try:
        lines = log.read_text(errors="replace").splitlines()
    except OSError:
        return []
    records: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            records.append(rec)
    return records


def _log_audit_once(root: Path, *, event: str, phase: str, detail: str) -> str:
    """Append a decision/telemetry audit record the moment it is earned.

    The protocol persists these at decision time, so a later gate stop or an
    idempotent batch skip can never lose them. Re-runs re-earn byte-identical
    records, so an existing record with the same (event, phase, detail) triple
    suppresses the append. Returns a short note for the gate detail.
    """
    for rec in _read_log_records(root):
        if rec.get("event") == event and rec.get("phase") == phase and rec.get("detail") == detail:
            return "已记录（去重）"
    try:
        append_event(root, build_record(event=event, phase=phase, detail=detail))
    except (EventLogError, OSError) as exc:
        return f"WARN: 审计事件写入失败（{exc}）"
    return "已记 EVENT-LOG"


def _batch_already_logged(root: Path, from_phase: str, to_phase: str) -> bool:
    """True iff this run is an idempotent re-run of an already-logged transition.

    The newest ``phase_start`` must name ``to_phase`` AND no phase-flow event
    (:data:`_FLOW_EVENTS`) for ``from_phase`` may follow it — such a record
    means the workflow went back to the source phase since, so the upcoming
    transition is a new one that deserves its own batch. A rollback performed
    with no events at all remains indistinguishable from a re-run; the
    recovery protocols log ``revision_start`` / ``incident`` for this reason.
    """
    records = _read_log_records(root)
    newest_idx: int | None = None
    newest_phase: str | None = None
    for i, rec in enumerate(records):
        if rec.get("event") == "phase_start" and rec.get("phase"):
            newest_idx, newest_phase = i, str(rec["phase"])
    if newest_idx is None or newest_phase != to_phase:
        return False
    return not any(
        rec.get("event") in _FLOW_EVENTS and rec.get("phase") == from_phase
        for rec in records[newest_idx + 1 :]
    )


def _gate_event_batch(
    root: Path, instruction_name: str, from_phase: str, to_phase: str
) -> GateResult:
    """Atomically append the 4-record transition batch.

    Idempotency: skipped when :func:`_batch_already_logged` recognises this
    run as a re-run of the same, already-logged transition. Audit records are
    not part of the batch — they are appended at decision time by
    :func:`_log_audit_once`.
    """
    gate = "event-batch"
    if _batch_already_logged(root, from_phase, to_phase):
        return GateResult(
            gate,
            OUTCOME_SKIP,
            f"newest phase_start is already {to_phase!r} — batch skipped (idempotent re-run)",
        )

    records = [
        build_record(
            event="phase_end", phase=from_phase, status="approved", detail="reviewer 通过"
        ),
        build_record(
            event="review_verdict",
            phase=from_phase,
            agent="reviewer",
            status="approved",
            detail="审查通过",
        ),
        build_record(
            event="state_change",
            phase=to_phase,
            detail=f"{instruction_name} 阶段更新: {from_phase} → {to_phase}",
        ),
        build_record(event="phase_start", phase=to_phase, detail=f"进入 {to_phase} 阶段"),
    ]
    try:
        path, count = append_batch(root, records)
    except (EventLogError, OSError) as exc:
        return GateResult(
            gate,
            OUTCOME_FAIL,
            f"event batch not written ({type(exc).__name__}: {exc}) — "
            "fix docs/EVENT-LOG.jsonl writability and re-run",
        )
    return GateResult(gate, OUTCOME_PASS, f"{count} event(s) appended to {path.name}")


def _gate_claude_md(root: Path, instruction_file: Path, to_phase: str, compact: bool) -> GateResult:
    """Instruction-file hygiene gate; ``compact`` applies the automatic fix."""
    gate = "claude-md"
    limits = ConfigManager(root).claude_md_limits
    name = instruction_file.name

    measurement = measure_claude_md(instruction_file)
    if not measurement.exists:
        return GateResult(
            gate, OUTCOME_SKIP, f"no {name} at {instruction_file} — hygiene gate skipped"
        )

    breaches = limit_breaches(measurement, limits)
    if not breaches:
        return GateResult(gate, OUTCOME_PASS, "within limits")

    compact_note = ""
    if compact:
        archive = root / ".cataforge" / "learnings" / "registry-archive.md"
        compaction = compact_learnings_registry(
            instruction_file,
            archive_path=archive,
            max_entries=limits["learnings_registry_max_entries"],
        )
        if compaction.rewrote_claude_md:
            # The mutation happened — audit it now, whatever the re-check says.
            try:
                append_event(
                    root,
                    build_record(
                        event="state_change",
                        phase=to_phase,
                        detail="claude-md compact applied at phase transition",
                    ),
                )
                compact_note = "compact applied (event logged)"
            except (EventLogError, OSError) as exc:
                compact_note = f"compact applied (WARN: 审计事件写入失败（{exc}）)"
        else:
            compact_note = "compact was a no-op"
        breaches = limit_breaches(measure_claude_md(instruction_file), limits)
        if not breaches:
            return GateResult(gate, OUTCOME_PASS, f"within limits after compact — {compact_note}")

    summary = ", ".join(f"{key}: {measured} > {limit}" for key, measured, limit in breaches)
    if compact_note:
        summary += f" · {compact_note}"
    options = (
        [GateOption("手动瘦身后重跑", f"编辑 {name} 收敛越界项后重跑本命令")]
        if compact
        else [
            GateOption("自动 compact", "重跑本命令并加 --compact（仅收敛 Learnings Registry）"),
            GateOption("手动瘦身后重跑", f"编辑 {name} 收敛越界项后重跑本命令"),
        ]
    )
    return GateResult(gate, OUTCOME_STOP, f"limits exceeded — {summary}", options=options)


def _dispatch_hint(root: Path, to_phase: str) -> dict[str, str] | None:
    """Dispatch hint for entering the next phase: role + execution_host."""
    if to_phase == "completed":
        return {"phase": to_phase, "hint": "7 阶段完成 — 按 §Retrospective 触发 reflector"}

    from cataforge.runtime.skill.builtins.framework_review._framework_data import (  # noqa: PLC0415
        read_workflow_modes,
    )

    mode = read_execution_mode(root) or "standard"
    for entry in read_workflow_modes(root).get(mode) or []:
        if entry.get("phase") == to_phase:
            return {
                "mode": mode,
                "phase": to_phase,
                "role": str(entry.get("role", "")),
                "execution_host": str(entry.get("execution_host", "")),
            }
    return None


__all__ = [
    "GateOption",
    "GateResult",
    "TransitionReport",
    "run_transition",
]
