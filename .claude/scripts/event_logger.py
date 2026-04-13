#!/usr/bin/env python3
"""CataForge Event Logger — 统一事件日志追加写入工具。

将结构化事件追加到 docs/EVENT-LOG.jsonl，作为审计追踪的单一事实来源。

用法 (CLI):
  python .claude/scripts/event_logger.py \\
    --event agent_dispatch \\
    --phase architecture \\
    --agent architect \\
    --task-type new_creation \\
    --detail "激活 architect 执行架构设计"

用法 (批量模式，从 stdin 读取 JSONL):
  echo '{"event":"phase_start","phase":"architecture","detail":"..."}
  {"event":"agent_dispatch","phase":"architecture","agent":"architect","detail":"..."}' | \\
    python .claude/scripts/event_logger.py --batch

用法 (Python 导入):
  from event_logger import append_event, append_events_batch
  append_event(event="agent_dispatch", phase="architecture",
               agent="architect", detail="激活 architect 执行架构设计")
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# 共享工具
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import ensure_utf8_stdio, find_project_root


# 以下枚举需与 .claude/schemas/event-log.schema.json 保持同步
VALID_EVENTS = {
    "session_start",
    "phase_start",
    "phase_end",
    "agent_dispatch",
    "agent_return",
    "review_verdict",
    "user_decision",
    "revision_start",
    "tdd_phase",
    "incident",
    "state_change",
    "correction",
    "doc_finalize",
}

VALID_STATUSES = {
    "completed",
    "needs_input",
    "blocked",
    "approved",
    "approved_with_notes",
    "needs_revision",
    "rolled-back",
}

VALID_TASK_TYPES = {
    "new_creation",
    "revision",
    "continuation",
    "retrospective",
    "skill-improvement",
    "apply-learnings",
    "amendment",
}


LOG_ROTATE_MAX_LINES = 2000
LOG_ROTATE_KEEP_LINES = 500


def _get_log_path():
    """Return the event log file path, respecting CATAFORGE_EVENT_LOG env var."""
    env_path = os.environ.get("CATAFORGE_EVENT_LOG")
    if env_path:
        return env_path
    return os.path.join(find_project_root(), "docs", "EVENT-LOG.jsonl")


def _maybe_rotate(log_path):
    """Rotate the event log if it exceeds LOG_ROTATE_MAX_LINES.

    Archives older entries to EVENT-LOG.{date}.jsonl and keeps the most
    recent LOG_ROTATE_KEEP_LINES entries in the active log file.
    """
    try:
        if not os.path.isfile(log_path):
            return
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) <= LOG_ROTATE_MAX_LINES:
            return

        # Archive older lines
        archive_name = log_path.replace(
            ".jsonl",
            f".{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.jsonl",
        )
        archived = lines[:-LOG_ROTATE_KEEP_LINES]
        kept = lines[-LOG_ROTATE_KEEP_LINES:]

        with open(archive_name, "w", encoding="utf-8") as f:
            f.writelines(archived)
        with open(log_path, "w", encoding="utf-8") as f:
            f.writelines(kept)
    except OSError:
        pass  # Rotation is best-effort; don't break logging


def append_event(
    event,
    phase,
    detail,
    agent=None,
    task_type=None,
    status=None,
    ref=None,
    log_path=None,
):
    """Append a structured event to the JSONL log file.

    Args:
        event: Event type (must be in VALID_EVENTS).
        phase: Current project phase.
        detail: Short event description.
        agent: Related agent directory name (optional).
        task_type: Agent dispatch task type (optional).
        status: Result status code (optional).
        ref: Document reference or file path (optional).
        log_path: Override log file path (optional).

    Returns:
        The event dict that was written.
    """
    if event not in VALID_EVENTS:
        raise ValueError(f"Invalid event '{event}', expected: {sorted(VALID_EVENTS)}")
    if status is not None and status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{status}', expected: {sorted(VALID_STATUSES)}"
        )
    if task_type is not None and task_type not in VALID_TASK_TYPES:
        raise ValueError(
            f"Invalid task_type '{task_type}', expected: {sorted(VALID_TASK_TYPES)}"
        )

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "phase": phase,
        "detail": detail,
    }
    if agent is not None:
        entry["agent"] = agent
    if task_type is not None:
        entry["task_type"] = task_type
    if status is not None:
        entry["status"] = status
    if ref is not None:
        entry["ref"] = ref

    target = log_path or _get_log_path()

    # Ensure parent directory exists
    parent_dir = os.path.dirname(target)
    if parent_dir and not os.path.isdir(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)

    with open(target, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    _maybe_rotate(target)
    return entry


def append_events_batch(events, log_path=None):
    """Append multiple structured events to the JSONL log file in a single open().

    Args:
        events: Iterable of dicts, each with keys matching append_event kwargs
            (event, phase, detail required; agent/task_type/status/ref optional).
        log_path: Override log file path (optional).

    Returns:
        List of entry dicts that were written.

    Raises:
        ValueError: If any event fails validation. No events are written on error.
    """
    validated = []
    for idx, item in enumerate(events):
        if not isinstance(item, dict):
            raise ValueError(
                f"Batch entry #{idx} must be a dict, got {type(item).__name__}"
            )
        event = item.get("event")
        phase = item.get("phase")
        detail = item.get("detail")
        if not event or not phase or detail is None:
            raise ValueError(
                f"Batch entry #{idx} missing required field(s): event/phase/detail"
            )
        if event not in VALID_EVENTS:
            raise ValueError(
                f"Batch entry #{idx}: invalid event '{event}', expected: {sorted(VALID_EVENTS)}"
            )
        status = item.get("status")
        if status is not None and status not in VALID_STATUSES:
            raise ValueError(
                f"Batch entry #{idx}: invalid status '{status}', expected: {sorted(VALID_STATUSES)}"
            )
        task_type = item.get("task_type")
        if task_type is not None and task_type not in VALID_TASK_TYPES:
            raise ValueError(
                f"Batch entry #{idx}: invalid task_type '{task_type}', expected: {sorted(VALID_TASK_TYPES)}"
            )

        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "phase": phase,
            "detail": detail,
        }
        for key in ("agent", "task_type", "status", "ref"):
            if item.get(key) is not None:
                entry[key] = item[key]
        validated.append(entry)

    target = log_path or _get_log_path()
    parent_dir = os.path.dirname(target)
    if parent_dir and not os.path.isdir(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)

    with open(target, "a", encoding="utf-8") as f:
        for entry in validated:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    _maybe_rotate(target)
    return validated


def main():
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="CataForge Event Logger — 追加事件到 docs/EVENT-LOG.jsonl"
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="批量模式: 从 stdin 读取 JSONL (每行一个事件)，一次性原子追加",
    )
    parser.add_argument(
        "--event",
        choices=sorted(VALID_EVENTS),
        help="事件类型 (单事件模式必填)",
    )
    parser.add_argument("--phase", help="当前项目阶段 (单事件模式必填)")
    parser.add_argument("--detail", help="事件简短描述 (单事件模式必填)")
    parser.add_argument("--agent", help="相关 Agent 目录名")
    parser.add_argument(
        "--task-type",
        choices=sorted(VALID_TASK_TYPES),
        help="任务类型",
    )
    parser.add_argument(
        "--status",
        choices=sorted(VALID_STATUSES),
        help="结果状态码",
    )
    parser.add_argument("--ref", help="文档引用或文件路径")

    args = parser.parse_args()

    if args.batch:
        events = []
        for lineno, raw in enumerate(sys.stdin, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as e:
                parser.error(f"stdin line {lineno} 不是合法 JSON: {e}")
        if not events:
            parser.error("--batch 模式下 stdin 未提供任何事件")
        entries = append_events_batch(events)
        print(
            json.dumps(
                {"batch_count": len(entries), "entries": entries},
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    missing = [k for k in ("event", "phase", "detail") if not getattr(args, k)]
    if missing:
        parser.error(
            f"单事件模式下缺少必填参数: {', '.join('--' + m for m in missing)}"
        )

    entry = append_event(
        event=args.event,
        phase=args.phase,
        detail=args.detail,
        agent=args.agent,
        task_type=args.task_type,
        status=args.status,
        ref=args.ref,
    )
    print(json.dumps(entry, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
