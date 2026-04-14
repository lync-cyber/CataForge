"""平台无关的数据类型定义。"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class AgentStatus(Enum):
    COMPLETED = "completed"
    NEEDS_INPUT = "needs_input"
    BLOCKED = "blocked"
    APPROVED = "approved"
    APPROVED_WITH_NOTES = "approved_with_notes"
    NEEDS_REVISION = "needs_revision"
    ROLLED_BACK = "rolled-back"


@dataclass
class DispatchRequest:
    agent_id: str
    task: str
    task_type: str
    input_docs: list[str]
    expected_output: str
    phase: str
    project_name: str
    background: bool = False
    max_turns: int | None = None
    review_path: str | None = None
    answers: dict | None = None
    intermediate_outputs: list[str] | None = None
    resume_guidance: str | None = None
    change_analysis: str | None = None


@dataclass
class AgentResult:
    status: AgentStatus
    outputs: list[str]
    summary: str
    questions: list[dict] | None = None
    completed_steps: str | None = None
    resume_guidance: str | None = None


CAPABILITY_IDS = [
    "file_read", "file_write", "file_edit", "file_glob", "file_grep",
    "shell_exec", "web_search", "web_fetch", "user_question", "agent_dispatch",
]
