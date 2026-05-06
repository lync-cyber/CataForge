---
name: framework-issue-resolve
description: "上游 GitHub issue 全闭环 — 拉取 → 审查分析 → 给修复意见 → 实施 → 关闭 issue。覆盖 framework-feedback bundle 的整段消化路径，把下游反馈打通到上游 SKILL-IMPROVE 应用 + close。本 skill 仅供 maintainer / fork owner 使用，不是下游业务流程的一部分。"
argument-hint: "[--repo OWNER/NAME] [--label LBL]... [--since YYYY-MM-DD] [--limit N] [--dry-run]"
suggested-tools: Read, Bash
depends: [framework-feedback]
disable-model-invocation: false
user-invocable: true
record-to-event-log: true
---

# 框架 issue 闭环消化 (framework-issue-resolve)

## 五步闭环

```
1. 拉取 (fetch)        →  cataforge issue triage [--dry-run]
2. 审查分析 (analyze)  →  draft 落 docs/reviews/triage/SKILL-IMPROVE-<id>-issue-<N>.md
3. 给修复意见 (propose)→  draft 内 verdict + rationale + 修复路径
4. 实施 (implement)   →  feature branch + Edit + commit + PR（标准 dev 流程）
5. 关闭 (close)        →  cataforge issue close <N> --verdict <v> [--pr <P>] [--reason ...]
```

每步之间是 maintainer **强制 checkpoint**：自动化只跨 1↔2 和 5；3↔4 是人工 go/no-go。

## 能力边界

- **能做**: 拉取 + Layer 1 字段解析 + 草稿渲染 + close 模板化（统一文案）
- **不做**: Layer 2 语义分析（仍是基于正则的字段抽取）；自动跨过 maintainer 实施 PR；自动改 issue label（用户/maintainer 手动）

## 输入规范

- `framework.json#upgrade.source.repo` — 拉取目标
- `framework.json#feedback.gh.labels` — 默认 label 过滤集合
- 本地 `.cataforge/skills/*` 和 `.cataforge/agents/*` — id 核对
- `cataforge.__version__` — reported_version vs installed_version 比对

## 输出规范

### Step 2 草稿 frontmatter

```yaml
---
id: SKILL-IMPROVE-<target_id>-issue-<N>
doc_type: skill-improve
status: triage-draft
source_issue: <N>
source_url: https://github.com/<owner>/<repo>/issues/<N>
reported_version: <X.Y.Z>
installed_version: <cataforge.__version__>
verdict: <见下表>
target_id: <skill/agent id, 或 source 文件名>
target_kind: skill | agent | source | schema | mixed | aggregate
target_path: <可选>
rationale: "..."
---
```

### verdict 五态

| verdict | 触发 | 后续动作 |
|---------|------|---------|
| `confirmed` | 引用了存在的 skill/agent/源文件 + reporter version 持平 | 写草稿；步骤 4 实施修复；步骤 5 close --verdict fixed |
| `wontfix-by-design` | maintainer 判定下游误解了主动设计（如带点 doc_id 被框架主动拒绝） | 草稿写出主动设计的 evidence；步骤 5 close --verdict wontfix --reason ... |
| `already-fixed` | reported_version < installed_version（自动判定） | 不写草稿；步骤 5 close --verdict already-fixed --pr <历史 PR> |
| `needs-repro` | body 缺 `cataforge --version` 行 | 不写草稿；评论要求 reporter 重跑 `cataforge feedback bug --gh`，加 label `needs-repro`（手动） |
| `unrelated` | 不像 feedback bundle | 不写草稿；可手动 close 为 off-topic |

> 注：自动 triage 只输出 `confirmed | already-fixed | needs-repro | unrelated`。`wontfix-by-design` 是 maintainer 在审查 confirmed 草稿后人工改写 frontmatter 的二次判定。

## 操作指令

### Step 1+2+3：拉取 + 分析 + 草稿

```bash
cataforge issue triage --dry-run                  # 看 verdict 分布
cataforge issue triage --since 2026-04-01         # 写草稿
cataforge issue triage --repo OWNER/NAME --label feedback   # fork owner 同步上游
```

### Step 4：实施

`confirmed` 草稿走标准 dev 流程：

```bash
git -c user.name=<id> -c user.email=<email> checkout -b <type>/<scope>-<topic>
# Edit / Write / 跑测试
git -c user.name=<id> -c user.email=<email> commit -m "<type>(<scope>): <subject>"
git -c user.name=<id> -c user.email=<email> push -u origin <branch>
gh pr create --title "<type>(<scope>): <subject>" --body "..."
```

`wontfix-by-design` 草稿不实施代码改动，可选地补 docs/reference FAQ 解释为什么。

### Step 5：关闭

```bash
# 修复后
cataforge issue close 104 --verdict fixed --pr 108
# → comment: "Fixed in v0.4.0 (PR #108). Triage: docs/reviews/triage/SKILL-IMPROVE-event-log-schema-issue-104.md"

# wontfix
cataforge issue close 102 --verdict wontfix --reason "doc_id 强制 slug 是主动设计；版本号入 frontmatter version 字段"
# → comment: "Wontfix — by design: doc_id 强制 slug 是主动设计；版本号入 frontmatter version 字段."

# 历史已修
cataforge issue close 99 --verdict already-fixed --pr 87
# → comment: "Already fixed in v0.3.0 (PR #87)."

# 干跑：只打印 comment 不真关
cataforge issue close 104 --verdict fixed --pr 108 --dry-run
```

## Layer 1 检查项

| ID | 标题 | 严重等级 |
|----|------|---------|
| triage_fetch | gh issue list 拉取 | info |
| triage_version_check | reported_version vs installed | info |
| triage_skill_ref_check | skill/agent id 是否仍存在 | info |
| triage_upstream_gap_count | upstream-gap 信号统计 | info |
| triage_draft_render | confirmed 写草稿 | fail |
| close_pr_required | fixed/already-fixed 必须 --pr | fail |
| close_reason_required | wontfix 必须 --reason | fail |

## Anti-Patterns

- **跳过 maintainer checkpoint 直接 close**：实施 PR 没合就 `cataforge issue close --verdict fixed` —— 会让下游收到错误的 "fixed in vX.Y.Z" 通知。close 必须在 PR merge **之后**。
- **wontfix 不写 evidence 就 close**：仅靠 `--reason` 一行不足以让下游理解为什么。先用 triage 草稿写完 evidence + 设计意图引用，close comment 链回草稿。
- **跳过 dry-run 直接写草稿到一个 PR 拉拉拉**：草稿数量大时 spam。先 `--dry-run` 检查噪声。
- **把 `triage-draft` 当 `reflector approved` 用**：它只是 Layer 1 事实核查产出，没经过 reflector evidence ≥2 校验，不能直接当 EXP 经验落地。需走 reflector → docs/reviews/retro/ → `learn: apply EXP-{NNN}` 路径。

## 与下游 framework-feedback 的回路

```
[下游] cataforge feedback bug --gh
   ↓ 创建 GitHub issue（带 framework.json#feedback.gh.labels 中的 label）
[上游] cataforge issue triage
   ↓ 写 docs/reviews/triage/SKILL-IMPROVE-…
[上游] reflector → docs/reviews/retro/
   ↓ apply EXP-NNN
[上游] PR merge
[上游] cataforge issue close <N> --verdict fixed --pr <P>
   ↓
[下游] cataforge upgrade apply
```
