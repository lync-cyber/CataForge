---
id: "ref-builtin-skill-layout"
doc_type: reference
author: framework
status: approved
deps: []
---

# Builtin Skill Layout

`src/cataforge/runtime/skill/builtins/<skill_id>/` 的目录骨架约定。所有新增 builtin skill 按本规范布局，框架审查（framework-review）的 B3 manifest drift 检查依赖此结构定位入口模块。

## 目录结构

```
src/cataforge/runtime/skill/builtins/<skill_id>/
├── __init__.py            # CHECKS_MANIFEST + 公共导出
├── <skill_id>_check.py    # CLI 入口 + main() + run()
├── _<helper>.py           # 私有 helper（前缀下划线，不外露）
├── checks/                # 多 check 时按家族拆分（可选）
│   ├── __init__.py
│   └── <family>.py
└── rules/                 # YAML 规则配置（可选）
    └── *.yaml
```

## 命名规范

- **包目录**: `snake_case` 与 SKILL.md 的 `name:` 对齐（连字符 → 下划线）。
- **入口模块**: `<skill_id>_check.py`（统一后缀 `_check`）。CLI 通过 `python -m cataforge.runtime.skill.builtins.<skill_id>.<skill_id>_check ...` 调用。
- **私有 helper**: `_<concept>.py` 前缀下划线，导入路径包内可见，包外不应直接 import。
- **check 家族**: 大于 5 个独立 check 时拆 `checks/<family>.py`，每个家族独立 import dataclasses，主入口 `__init__.py` 维护 `CHECKS_MANIFEST` 单一事实源。
- **rules YAML**: `rules/<concept>-<lang>.yaml`（语言相关）或 `rules/<concept>.yaml`（语言无关）。

## __init__.py 契约

- 必须导出 `CHECKS_MANIFEST: tuple[dict[str, str], ...]`，每项含 `id` / `title` / `severity`。
- `id` 命名: `<skill_namespace>.<check_specifier>`（如 `code_lint.ruff` / `B1_required_sections` / `e2e_scan.empty_token`）。命名空间在同一 builtin 内保持一致。
- 不在 `__init__.py` 写实现 — 仅 manifest 和 re-export。

## 入口模块契约

`<skill_id>_check.py` 必须提供:

- `run(...)` 函数：核心逻辑，返回 int exit code（0=PASS、1=FAIL、2=usage error）。
- `main()` 函数：argparse + 调用 `ensure_utf8()` + 调用 `run()`。
- `__main__` block：`if __name__ == "__main__": main()`。
- 公开 dataclass / 公共 API 通过 `__all__` 显式导出，方便其他 builtin 或 framework-review 引用。

## 与 framework-review B3 对账

每个 builtin 的 `CHECKS_MANIFEST` 与对应 SKILL.md `## Layer 1 检查项` 段双向校验：

- **Anchor mode**: SKILL.md 用 `<!-- check_id: X -->` 锚点，B3-α 校验 `X ∈ CHECKS_MANIFEST.id`。
- **Delegation mode**: SKILL.md 出现 `权威清单见 ...CHECKS_MANIFEST` 句，跳过逐条校验。

新 builtin 加入后必须在 SKILL.md 选其一，否则 B3 FAIL。

## 现状

按本规范 `<skill_id>_check.py` 入口形态：

| Skill | 入口模块 |
|-------|----------|
| `code_review` | `code_review/code_lint.py` |
| `doc_review` | `doc_review/doc_check.py` |
| `framework_review` | `framework_review/framework_check.py` |
| `sprint_review` | `sprint_review/sprint_check.py` |
| `framework_feedback` | `framework_feedback/framework_feedback.py` |
| `task_dep_analysis` | `task_dep_analysis/task_dep_analysis.py` |
| `testing` | `testing/e2e_scan.py` |

`code_lint` / `e2e_scan` / `task_dep_analysis` / `framework_feedback` 入口模块与 `<skill_id>_check.py` 后缀不一致，按现状保留；新增 builtin 一律按本规范命名。
