"""Task lifecycle through the authoring doors: a Sprint's tasks move through
the legal state machine, illegal moves are rejected with actionable errors,
and the deliberate-override path stays available.

This is the integration half of `tests/kg/test_slot_guard.py`: everything here
drives `application.context.write` / the `context update` CLI the way the
tdd-engine skill instructs the orchestrator to.
"""

from __future__ import annotations

import gc
import json
from pathlib import Path

import pytest

from cataforge.application.context import write as cw
from cataforge.domain.kg import KGConfig, KnowledgeGraph, init_store
from cataforge.domain.kg._dispatch import invalidate_cache
from cataforge.domain.kg._errors import KGValidationError


@pytest.fixture(autouse=True)
def _clear_caches():
    invalidate_cache()
    gc.collect()
    yield
    invalidate_cache()
    gc.collect()


def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "p"
    (proj / ".cataforge").mkdir(parents=True)
    (proj / "docs").mkdir()
    cfg = KGConfig(
        store_backend="oxigraph",
        db_path=proj / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "dev-plan"},
    )
    handle = init_store(cfg, force=True)
    handle.raw.flush()
    handle.close()
    (proj / ".cataforge" / "framework.json").write_text(
        json.dumps(
            {"context": {"mode": "graph", "kg_active_doc_types": ["prd", "arch", "dev-plan"]}}
        ),
        encoding="utf-8",
    )
    invalidate_cache()
    gc.collect()
    return proj


def _task_status(proj: Path, entity_id: str) -> str | None:
    cfg = KGConfig(
        store_backend="oxigraph",
        db_path=proj / ".cataforge" / "kg" / "store",
        kg_active_doc_types={"prd", "arch", "dev-plan"},
    )
    ns = cfg.ontology_namespace.rstrip("/") + "/"
    with KnowledgeGraph.connect(cfg) as kg:
        rows = list(
            kg.store.query(
                f'PREFIX cf: <{ns}> SELECT ?s WHERE {{ ?t cf:entity_id "{entity_id}" ; '
                "cf:task_status ?s }"
            )
        )
    return str(rows[0]["s"].value) if rows else None


def test_full_task_lifecycle_todo_to_done(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    cw.author_entity(
        str(proj),
        entity_id="T-001",
        class_name="Task",
        title="登录端到端切片",
        slots={"task_status": "todo"},
    )
    gc.collect()
    for step in ("in_progress", "review", "done"):
        cw.update_entity(str(proj), "T-001", slots={"task_status": step})
        gc.collect()
    assert _task_status(proj, "T-001") == "done"


def test_illegal_jump_todo_to_done_is_rejected(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    cw.author_entity(
        str(proj), entity_id="T-002", class_name="Task", title="卡片", slots={"task_status": "todo"}
    )
    gc.collect()
    with pytest.raises(KGValidationError, match="illegal task_status transition 'todo' → 'done'"):
        cw.update_entity(str(proj), "T-002", slots={"task_status": "done"})
    gc.collect()
    assert _task_status(proj, "T-002") == "todo", "rejected update must not mutate the store"


def test_terminal_state_reopen_requires_ack(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    cw.author_entity(
        str(proj), entity_id="T-003", class_name="Task", title="卡片", slots={"task_status": "done"}
    )
    gc.collect()
    with pytest.raises(KGValidationError, match="ack-status-jump"):
        cw.update_entity(str(proj), "T-003", slots={"task_status": "in_progress"})
    gc.collect()
    cw.update_entity(str(proj), "T-003", slots={"task_status": "in_progress"}, ack_status_jump=True)
    gc.collect()
    assert _task_status(proj, "T-003") == "in_progress"


def test_enum_stranger_rejected_at_authoring(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    with pytest.raises(KGValidationError, match="allowed values"):
        cw.author_entity(
            str(proj),
            entity_id="T-004",
            class_name="Task",
            title="卡片",
            slots={"task_status": "doing"},
        )


def test_wrong_slot_vocabulary_rejected_on_update(tmp_path: Path) -> None:
    # The historical drift `--slot status=done` (artifact lifecycle slot fed a
    # task execution state) must fail loudly instead of corrupting silently.
    proj = _project(tmp_path)
    cw.author_entity(str(proj), entity_id="T-005", class_name="Task", title="卡片")
    gc.collect()
    with pytest.raises(KGValidationError, match="Task.status rejects 'done'"):
        cw.update_entity(str(proj), "T-005", slots={"status": "done"})


def test_cli_update_denies_illegal_jump_with_actionable_error(tmp_path: Path) -> None:
    from cataforge.interface.cli.context._group import context_group
    from tests.cli.conftest import invoke_under_group

    proj = _project(tmp_path)
    cw.author_entity(
        str(proj), entity_id="T-006", class_name="Task", title="卡片", slots={"task_status": "todo"}
    )
    gc.collect()

    denied = invoke_under_group(
        context_group,
        ["update", "T-006", "--slot", "task_status=done", "--project-root", str(proj)],
    )
    exit_code, output = denied.exit_code, denied.output
    # The Result's exc_info chain pins the store handle; drop it so the
    # process-local oxigraph lock releases before the follow-up read.
    del denied
    gc.collect()
    assert exit_code != 0
    assert "illegal task_status transition" in output
    assert "--ack-status-jump" in output
    assert _task_status(proj, "T-006") == "todo"


def test_cli_update_ack_flag_allows_deliberate_jump(tmp_path: Path) -> None:
    from cataforge.interface.cli.context._group import context_group
    from tests.cli.conftest import invoke_under_group

    proj = _project(tmp_path)
    cw.author_entity(
        str(proj), entity_id="T-007", class_name="Task", title="卡片", slots={"task_status": "todo"}
    )
    gc.collect()

    acked = invoke_under_group(
        context_group,
        [
            "update",
            "T-007",
            "--slot",
            "task_status=done",
            "--ack-status-jump",
            "--project-root",
            str(proj),
        ],
    )
    assert acked.exit_code == 0, acked.output
    gc.collect()
    assert _task_status(proj, "T-007") == "done"
