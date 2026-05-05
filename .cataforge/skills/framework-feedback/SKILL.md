---
name: framework-feedback
description: "框架反馈打包 — 把下游项目使用 CataForge 时发现的问题 / 改进建议 / 偏离上游基线的纠偏，打包成 upstream-ready 的 markdown bundle，回流到 CataForge 仓库。区别于下游项目自身的用户反馈渠道：本 skill 仅针对 CataForge 框架本体（CLI / scaffold / agents / skills / hooks / docs）。当用户提到反馈框架问题、提交 CataForge issue、上游 baseline 不准确、累积 upstream-gap 想批量回报时使用。"
argument-hint: "<kind: bug|suggest|correction-export> [--summary TEXT] [--out PATH] [--since YYYY-MM-DD] [--threshold N]"
suggested-tools: Read, Bash
depends: [framework-review]
disable-model-invocation: false
user-invocable: true
record-to-event-log: true
---

# 框架反馈打包 (framework-feedback)

## 能力边界
- 能做: 聚合 `cataforge --version` + `doctor` + 最近 N 条 EVENT-LOG + `CORRECTIONS-LOG deviation=upstream-gap` + `framework-review` Layer 1 FAIL 摘要；渲染为 markdown；脱敏路径；通过 `--print` / `--out` / `--clip` / `--gh` 四选一发出
- 不做: 修复发现的问题（仅打包反馈）；处理下游项目自身的产品反馈（与本 skill 无关）；自动发起 GitHub issue（除非显式 `--gh`，且需本机已装并登录 `gh`）

## 输入规范
- kind: `bug` | `suggest` | `correction-export`
- 项目根下的 `.cataforge/` + `docs/EVENT-LOG.jsonl` + `docs/reviews/CORRECTIONS-LOG.md`（任一缺失都降级为部分 bundle，不阻断）
- `cataforge.core.feedback`（assembler；CLI 与本 skill 共用同一份逻辑）

## 输出规范
- 默认: stdout 渲染 markdown body
- `--out PATH`: 写到指定文件（相对路径解析在项目根下）
- 上游 issue 模板: `.github/ISSUE_TEMPLATE/feedback-from-cli.yml`（字段与本 bundle 一一对应，方便上游分诊）
- EVENT-LOG: 每次运行写一条 `state_change` 事件（`record-to-event-log: true`），ref=`skill:framework-feedback/framework_feedback`

## 推荐触发路径

framework-feedback 是按需触发的反馈打包 skill，**不进入业务流程主循环**。推荐的合规触发面：

- **用户手动**: `cataforge feedback bug --gh`（或 `suggest` / `correction-export`）
- **orchestrator 自动**: 当累计 `upstream-gap` 数 ≥ `RETRO_TRIGGER_UPSTREAM_GAP_DEFAULT`（默认 3）时，orchestrator 调起 `cataforge skill run framework-feedback -- correction-export --out docs/feedback/<ts>.md`（reflector 只读，本 skill 需要 `shell_exec`，故由 orchestrator 持有）。落盘后由用户决定是否上报
- **doctor 报告 FAIL 后**: `cataforge feedback bug --print | tee docs/feedback/doctor-fail-<ts>.md`
- **不要**: 让 reviewer / implementer 在业务流程内自动调起（与业务 review 报告不是同一资源）

## 操作指令: 上游反馈打包 (feedback)

### Step 1: 触发选择 kind
- 出现可复现 bug / 异常退出 / 部署后失败 → `bug`
- 框架行为符合预期但流程笨重 / 缺特性 → `suggest`
- 累计多条 `deviation=upstream-gap` 纠偏 → `correction-export`

### Step 2: 调用 Layer 1 打包脚本
**调用约定（单一入口）**: 一律通过 `cataforge skill run framework-feedback -- <kind> [--summary ...]` 触发，由框架解析 SKILL.md 元数据并派发到 builtin 脚本。**不得**直接 `python .cataforge/skills/.../scripts/*.py`——该路径为框架内部实现细节，不保证存在。

执行示例:

```bash
# bug 反馈到 stdout
cataforge skill run framework-feedback -- bug --summary "deploy 后 hook 不触发"

# 建议写盘等待复核
cataforge skill run framework-feedback -- suggest \
    --summary "希望支持 --dry-run 预览" \
    --out docs/feedback/suggest-$(date +%Y%m%d).md

# 上游反馈聚合 (仅当 upstream-gap 数 ≥ threshold)
cataforge skill run framework-feedback -- correction-export --threshold 3
```

### Step 3: 上游通道选择
推荐使用 CLI 同等命令直接触发上游通道（skill 仅产 markdown，不直接发 issue）:

```bash
cataforge feedback bug --gh        # 通过 gh 直接开 issue
cataforge feedback bug --clip      # 拷剪贴板，手动粘贴到 GitHub
cataforge feedback bug --out feedback.md  # 落盘
```

### Step 4: 隐私
- 默认会把 `<project>` 与 `~` 路径替换占位符
- 仅在内部反馈 / 自托管 GitHub 时考虑加 `--include-paths`

## Layer 1 检查项
| ID | 标题 | 严重等级 |
|----|------|---------|
| feedback_env | 环境采集 (package + scaffold + python + os + runtime_platform) | info |
| feedback_doctor_summary | cataforge doctor FAIL/WARN 行抽取 | info |
| feedback_event_tail | EVENT-LOG.jsonl 尾部 N 条 (默认 20，可 --since 过滤) | info |
| feedback_correction_aggregate | CORRECTIONS-LOG deviation=upstream-gap 聚合 | info |
| feedback_framework_review | framework-review Layer 1 FAIL 摘要 (best-effort) | info |
| feedback_redaction | 路径脱敏 (~ / <project>，--include-paths 显式关闭) | fail |
| feedback_sinks | 输出通道 --print / --out / --clip / --gh 互斥校验 | fail |

权威清单见 `cataforge.skill.builtins.framework_feedback.CHECKS_MANIFEST`。

## Anti-Patterns
- 把下游项目自身的用户反馈走这条 skill —— 本 skill 仅打包"对 CataForge 框架"的反馈
- 在没有 `gh` CLI 时强行 `--gh` —— 会直接 ExternalToolError，应回退 `--clip` 或 `--print`
- 用 `--include-paths` 输出后直接贴公开 issue —— 会泄漏本机目录结构
- 没有 `upstream-gap` 纠偏时跑 `correction-export` —— 该子命令会拒绝（exit 1）以防止空 bundle
