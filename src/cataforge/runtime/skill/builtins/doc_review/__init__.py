"""Built-in doc-review skill.

``CHECKS_MANIFEST`` mirrors the actual checks executed by ``checker.py``
and the typed-doc mixin. doc-review is a builtin-only engine with no
standalone SKILL.md — its prose surface lives in the context skill's
review reference, which delegates the authoritative check list here.
"""

from __future__ import annotations

CHECKS_MANIFEST: tuple[dict[str, str], ...] = (
    {
        "id": "check_export_freshness",
        "title": "graph 模式: 被审文件为最新一致导出 (无 graph_ahead/conflict/节不一致)",
        "severity": "fail",
    },
    {
        "id": "check_meta",
        "title": "文档头元数据完整 (id / author / status / deps / consumers)",
        "severity": "fail",
    },
    {
        "id": "check_nav_block",
        "title": "[NAV]块存在且与实际章节一致 (changelog/research 除外)",
        "severity": "fail|warn",
    },
    {
        "id": "check_no_todo",
        "title": "无未处理 TODO/TBD/FIXME (或已标注 [ASSUMPTION])",
        "severity": "fail",
    },
    {
        "id": "check_xref",
        "title": "交叉引用目标文件存在",
        "severity": "fail",
    },
    {
        "id": "check_line_count",
        "title": "文档行数 ≤ DOC_SPLIT_THRESHOLD_LINES (超过则建议拆分为多个逻辑文档)",
        "severity": "warn",
    },
    {
        "id": "check_required_sections",
        "title": "所有必填章节存在且非空 (按 doc_type / mode)",
        "severity": "fail",
    },
    {
        "id": "check_id_continuity",
        "title": "条目 ID 编号连续无跳号 (F-/M-/API-/E-/T-/C-/P-)",
        "severity": "warn",
    },
    {
        "id": "check_bidirectional_coverage",
        "title": ("双向覆盖: 下游文档覆盖上游所有 item (arch↔prd / dev-plan↔arch / ui-spec↔prd)"),
        "severity": "fail",
    },
    {
        "id": "check_prd",
        "title": "prd 专项: 用户故事/AC-NNN/非功能需求/优先级",
        "severity": "fail|warn",
    },
    {
        "id": "check_arch",
        "title": "arch 专项: F-NNN 引用/API 含 request/实体含字段表/技术栈选型理由",
        "severity": "fail|warn",
    },
    {
        "id": "check_dev_plan",
        "title": "dev-plan 专项: 依赖无环/tdd_acceptance/deliverables/context_load",
        "severity": "fail|warn",
    },
    {
        "id": "check_ui_spec",
        "title": "ui-spec 专项: §0 设计方向/组件变体/页面构成/Token 数量",
        "severity": "fail|warn",
    },
    {
        "id": "check_test_report",
        "title": "test-report 专项: 测试金字塔/用例矩阵/覆盖率/缺陷清单/结论",
        "severity": "fail|warn",
    },
    {
        "id": "check_deploy_spec",
        "title": "deploy-spec 专项: 构建流程/dev+prod 环境/发布检查清单",
        "severity": "fail|warn",
    },
    {
        "id": "check_research",
        "title": "research-note 专项: 调研方法模式/结论非空",
        "severity": "fail|warn",
    },
    {
        "id": "check_changelog",
        "title": "changelog 专项: 版本条目/Added/Changed/Fixed 分类",
        "severity": "fail|warn",
    },
)
