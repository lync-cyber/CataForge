"""Built-in framework-feedback skill.

Bridges downstream-discovered issues / improvement suggestions back to
the **CataForge framework** upstream. Distinct from any project-local
feedback channel the downstream may have for its own product:

* ``framework-feedback`` targets defects / gaps in CataForge itself
  (CLI, scaffold, agents, skills, hooks, docs).
* The downstream project's own user-feedback flow stays untouched.

``CHECKS_MANIFEST`` declares the bundle slices the underlying
``cataforge.core.feedback`` assembler can produce, so ``framework-review``
B3 can verify the SKILL.md prose and this manifest stay aligned.
"""

from __future__ import annotations

CHECKS_MANIFEST: tuple[dict[str, str], ...] = (
    {
        "id": "feedback_env",
        "title": "环境采集 (package + scaffold + python + os + runtime_platform)",
        "severity": "info",
    },
    {
        "id": "feedback_doctor_summary",
        "title": "cataforge doctor FAIL/WARN 行抽取",
        "severity": "info",
    },
    {
        "id": "feedback_event_tail",
        "title": "EVENT-LOG.jsonl 尾部 N 条 (默认 20，可 --since 过滤)",
        "severity": "info",
    },
    {
        "id": "feedback_correction_aggregate",
        "title": "CORRECTIONS-LOG deviation=upstream-gap 聚合",
        "severity": "info",
    },
    {
        "id": "feedback_framework_review",
        "title": "framework-review Layer 1 FAIL 摘要 (best-effort)",
        "severity": "info",
    },
    {
        "id": "feedback_redaction",
        "title": "路径脱敏 (~ / <project>，--include-paths 显式关闭)",
        "severity": "fail",
    },
    {
        "id": "feedback_sinks",
        "title": "输出通道 --print / --out / --clip / --gh 互斥校验",
        "severity": "fail",
    },
)
