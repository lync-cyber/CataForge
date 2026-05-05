---
name: framework-issue-triage
description: "上游 GitHub issue 分诊 — 从 CataForge 仓库拉 open issue（默认按 feedback label 过滤），事实核查 + 合理性分析后产出 SKILL-IMPROVE 草稿。闭环 framework-feedback → upstream issue → SKILL-IMPROVE 改造路径。本 skill 仅供 maintainer / fork owner 使用，不是下游业务流程的一部分。"
argument-hint: "[--repo OWNER/NAME] [--label LBL]... [--since YYYY-MM-DD] [--limit N] [--dry-run]"
suggested-tools: Read, Bash
depends: [framework-feedback]
disable-model-invocation: false
user-invocable: true
record-to-event-log: true
---

# 框架 issue 分诊 (framework-issue-triage)

## 能力边界

- **能做**: `gh issue list` 拉 open issue → 解析 issue body 的 `cataforge --version` / `framework-review FAIL` / `upstream-gap` 字段 → 版本比对 + 本地 skill/agent id 核对 → 写 `docs/reviews/triage/SKILL-IMPROVE-<id>-issue-<N>.md` 草稿（`status: triage-draft`）
- **不做**: `gh issue close` / `comment`（外发动作 maintainer 手动）；Layer 2 语义分析（仅做基于正则的字段抽取）；修 issue 本身；下游产品 issue

## 输入 / 输出

- 输入：`framework.json#upgrade.source.repo` 拉取目标 + `feedback.gh.labels` 过滤；本地 `.cataforge/skills/*` 和 `.cataforge/agents/*` 用于 id 核对；`cataforge.__version__` 用于版本比对
- 输出：`docs/reviews/triage/SKILL-IMPROVE-<id>-issue-<N>.md` 草稿（frontmatter 含 `source_issue` / `reported_version` / `installed_version` / `verdict` / `rationale`）；终端按 verdict 着色一行一条

## verdict

| verdict | 触发条件 | 动作 |
|---------|---------|------|
| `confirmed` | 引用了存在的 skill/agent 且无 version skew | 写草稿 |
| `already-fixed` | `reported_version < installed_version` | 不写草稿；issue 上挂已修复版本 |
| `needs-repro` | body 里没有 `cataforge --version` 行 | 不写草稿；要求 reporter 重跑 `cataforge feedback bug --gh` |
| `unrelated` | 不像 feedback bundle（无 env / 无 review 引用 / 无 gap） | 不写草稿 |

## 推荐触发路径

maintainer 侧手动工具，不进入 orchestrator 业务循环。前置：`gh auth status` 通过；本地 `.cataforge/skills/` + `.cataforge/agents/` 完整（用于 id 核对）。

## 操作指令

```bash
cataforge issue triage --dry-run                  # 看 verdict 分布
cataforge issue triage --since 2026-04-01         # 写草稿
cataforge issue triage --repo OWNER/NAME --label feedback   # fork owner 同步上游
```

`confirmed` issue 写 `docs/reviews/triage/SKILL-IMPROVE-<id>-issue-<N>.md`。maintainer 审核后把可执行的迁到 `docs/reviews/retro/`，按标准 reflector apply 流程提交：`learn: apply EXP-{NNN} to {target_file}`。

收尾动作（外发，maintainer 手动）：
- `confirmed` 修复后：`gh issue close <N> --comment "Fixed in vX.Y.Z"`
- `already-fixed`：`gh issue close <N> --comment "Already fixed in vX.Y.Z"`
- `needs-repro`：评论要求 reporter 重跑 `cataforge feedback bug --gh`，加 label `needs-repro`

## Layer 1 检查项

| ID | 标题 | 严重等级 |
|----|------|---------|
| triage_fetch | gh issue list 拉取（按 label / state / since 过滤） | info |
| triage_version_check | reported_version vs installed cataforge 版本对比 | info |
| triage_skill_ref_check | issue 引用的 skill_id / agent_id 是否仍存在 | info |
| triage_upstream_gap_count | upstream-gap 信号数量统计 | info |
| triage_draft_render | confirmed verdict 写 SKILL-IMPROVE 草稿 | fail |

## Anti-Patterns

- 直接让本 skill `gh issue close` —— 必须 maintainer 手动执行（涉及对外动作）
- 跳过 dry-run 直接写草稿到一个 PR —— 草稿数量大时会 spam，先 dry-run 检查噪声
- 把 `triage-draft` 当 `reflector approved` 用 —— 它只是 Layer 1 事实核查产出，没经过 reflector 的 evidence ≥2 校验，不能直接当 EXP 经验落地
