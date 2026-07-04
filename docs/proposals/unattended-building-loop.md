# 提案：无人值守 building loop — Ralph 式外循环嫁接 orchestrator

> 状态：设计草稿，待实施授权。关键决策见 §6 决策记录；本文为方案与规约，不含已落地代码。
> 范围：新增一层「跨会话、fresh-context」的无人值守执行外壳，**仅驱动 `development` 阶段对一个已冻结 sprint 的 building**。复用既有 TDD / code-review 门禁、`EVENT-LOG.jsonl`、dev-plan 任务卡、orchestrator Startup / Recovery 协议，**不新建质量层**。明确排除：PRD / ARCH / DEV-PLAN 的 authoring（planning 永远留给有人的白天 + doc-review）。
> 交付边界：方案、借/不借决策表、外循环脚本（参考实现）、新增框架配置常量、`EVENT-LOG` schema 扩展、运维 metrics schema 为本文职责；实施代码与守卫以后续 PR 为准。

---

## 0. 总体判断

Ralph（Wiggum）循环与 CataForge 在最深的一层**殊途同归**：二者都把跨迭代需要存活的状态从 LLM context 挪到**文件 + git**，让 agent 可以「失忆后读盘重建」。差异在于侧重点——Ralph 偏极简 / 涌现 / 可丢弃，CataForge 偏结构化 / 门禁 / 可审计；二者适用场景不同，非对立。

CataForge 已具备 Ralph 所需的两块地基：**状态外置**（§项目状态 + `docs/` + git + `EVENT-LOG.jsonl`）与**背压门禁**（TDD RED/GREEN + code-review/doc-review）。它缺的不是 Ralph 的世界观，而是三样薄外壳：

1. **外循环驱动** —— 一个「主线程可以死、靠文件从零重建」的跨会话循环；CataForge 现有 recovery 协议全部假设 orchestrator 主线程仍在单次会话内存活。
2. **无进展熔断** —— Ralph/frankbria 的 circuit breaker；CataForge 只有「反复问问题」维度（needs_revision 计数），无「反复失败 / 原地打转」维度的自动熔断，无人值守过夜会烧 token。
3. **机器可判的完成契约** —— Ralph 的 `completion-promise` / `EXIT_SIGNAL`；CataForge 的 sprint 完成判定散在 orchestrator 的语义推断里，外壳无确定性退出依据。

本提案在**不牺牲门禁内核**的前提下补齐这三样，把无人值守续航能力限定为 `development` 阶段的 building 引擎。

## 1. 设计来源与定位

### 1.1 Ralph 机制要点（借鉴对象）

| 机制 | 内核 |
|------|------|
| stateless agent + stateful filesystem | 进度只在文件 + git，context 每轮清空，agent 读盘重建 |
| 外循环 = 无智能调度器 | `while :; do cat PROMPT.md \| claude -p; done`，每轮 fresh process |
| 状态契约 | `specs/*`（冻结需求）/ `IMPLEMENTATION_PLAN.md`（演化任务，做完即 drain）/ `AGENTS.md`（操作手册，无进度） |
| 双向 steering | 上游=代码模式/工具范例；下游=tests/lint 背压拒绝无效产出 |
| 子代理=内存延伸 | 读用大量并行子代理、build/test 用单子代理做串行背压瓶颈，主 context 留在 smart zone |
| 退出 / 收敛 | `--completion-promise` + Stop hook（官方插件）；双条件门 + circuit breaker（生产实现） |
| 可丢弃性 | plan 廉价可再生；planning 与 building 两 mode 共享机制但严格分离 |
| 安全 | `--dangerously-skip-permissions` 必须配沙盒 + 最小权限 + git 兜底 |

### 1.2 在 CataForge 执行模式矩阵中的定位

CataForge 的执行模式矩阵本就内置了 Ralph↔门禁的光谱：`agile-prototype`（checkpoints=`none`、implementer 主线程内联、跳过 RED/GREEN 子代理）≈ Ralph 哲学；`standard`（重门禁）≈ 严肃交付。

本提案的无人值守外循环主场景为 **`standard` / `agile-lite` 模式下「已过 `pre_dev` 检查点、dev-plan 经 doc-review 冻结」之后某个 sprint 的 building 阶段**（完成契约 `ref=dev-plan#sprint-N`）。`agile-prototype` 无 sprint 分组（brief.md §5 直接是任务卡），其支持为后续接线（U-5）：`ref` 改用 `brief#tasks`，且无人循环期间禁止改 brief.md §任务卡（与冻结纪律一致）。外循环不进入 planning，不路由 Phase 1~4。

## 2. 借 / 不借 决策表

| 维度 | Ralph 怎么做 | CataForge 取舍 | 落点 |
|------|-------------|---------------|------|
| 状态外置 | 文件 + git | ✅ 已有，复用 | §3.2 |
| 外循环驱动 | bash `while` + `claude -p` fresh context | ⭐ **借**：无人值守 building 外壳 | §3.1 / §4.4 |
| 背压质量 | tests/lint 拒绝 | ✅ 已有（TDD + review），复用，不另造 | §3.5 |
| 无进展熔断 | circuit breaker（no-progress / same-error / output-decline） | ⭐ **借**：stagnation 自动熔断 | §3.4 / §4.1 |
| 完成信号 | completion-promise / EXIT_SIGNAL | ⭐ **借**：`sprint_complete` 事件契约 | §3.3 / §4.2 |
| 可观测 | metrics.jsonl + tmux dashboard | ⭐ **借**：per-loop 运维指标流 | §4.3 |
| 子代理=内存延伸 | 读 N 并行、build 1 串行 | ⭐ **借**：只读分析外包子代理、结论回主线程 | §3.1 |
| plan 可丢弃 | 随意重生 | ❌ **不借**：dev-plan 经 doc-review 冻结，是质量锚 | §1.2 / §5 |
| planning/building 两 mode 分离 | 共享机制 | ⭐ **借**（反向用）：无人只跑 building，planning 留白天 | §1.2 |
| skip-permissions | 沙盒兜底、纯涌现质量 | ⚠️ 借**外壳**：沙盒化，但保留 review 门禁内核、不自动 merge | §5 |
| 放任涌现（let Ralph Ralph） | 反应式调 | ⚠️ 仅限 agile-prototype / 已冻结 building，不套全流程 | §1.2 |

## 3. 架构

### 3.1 三层结构

```
┌─ 外壳（unattended-building-loop.sh，无智能调度器）────────────┐
│  while 未完成 且 未熔断 且 未达上限:                          │
│     snapshot(git HEAD, EVENT-LOG 行数)                       │
│     claude -p "<building prompt>"   ← 每轮 fresh context     │
│     探测完成 / 熔断 / 进展                                    │
└───────────────────────────┬─────────────────────────────────┘
                            ▼ 每轮拉起
┌─ orchestrator（Startup Protocol 读 §项目状态 + dev-plan 续位）┐
│  Mode Routing → development；取下一张 pending 任务卡          │
│  经 tdd-engine 跑 RED/GREEN/REFACTOR；GREEN 后 code-review    │
│  approved → 任务卡 status=done + git commit（feature 分支）   │
│  全卡 approved → emit sprint_complete 事件                    │
└───────────────────────────┬─────────────────────────────────┘
                            ▼ dispatch（独立上下文）
        test-writer / implementer / refactorer / reviewer 子代理
```

主 agent（orchestrator）退化为「调度器」，昂贵的只读分析（扫 dev-plan、查依赖、读审查历史）外包给一次性子代理、只收结论，保持主线程 context 清爽——这是 Ralph「子代理=内存延伸」对长跑无人值守的直接价值。

### 3.2 状态契约（复用，零新建数据层）

| 角色（Ralph） | CataForge 既有对应 | 性质 |
|--------------|-------------------|------|
| `specs/*`（冻结需求） | PRD / ARCH（已冻结）+ dev-plan 任务卡 AC | 不变（上游冻结） |
| `IMPLEMENTATION_PLAN.md`（演化任务） | dev-plan 任务卡 `status` 字段 + task-dep-analysis 排序 | 演化（status 推进即 drain） |
| `AGENTS.md`（操作手册） | `CLAUDE.md §执行环境`（install/test/lint 命令） | 缓慢演化 |
| git history（自审输入） | feature 分支 squash 前的迭代 commit | 自审 |
| 跨迭代审计 | `EVENT-LOG.jsonl`（语义事件） | 追加 |

外壳读 `EVENT-LOG.jsonl` 判完成 / 熔断，读 `git HEAD` 判进展；不引入新的事实源。

### 3.3 完成契约：`sprint_complete` 事件

orchestrator 在「目标 sprint 全部任务卡 code-review `approved`」时，写一条语义事件到 `EVENT_LOG_PATH`；外壳读该事件作为**确定性退出依据**，不依赖解析 LLM 输出文本推断完成状态。

emit（orchestrator 侧，复用既有 `cataforge event log` 入口）：

```bash
cataforge event log \
  --event sprint_complete --phase development --agent orchestrator \
  --ref "dev-plan#sprint-2" \
  --detail "sprint-2 全部 6 张任务卡 code-review approved；feature 分支 feat/sprint-2 待 PR"
```

事件行（符合扩展后的 `EVENT_LOG_SCHEMA`，见 §4.2）：

```json
{"ts":"2026-06-23T02:14:07+08:00","event":"sprint_complete","phase":"development","agent":"orchestrator","ref":"dev-plan#sprint-2","detail":"sprint-2 全部 6 张任务卡 code-review approved；feature 分支 feat/sprint-2 待 PR"}
```

`ref` 携带 sprint 标识（`dev-plan#sprint-N`），是外壳匹配「本次目标 sprint 是否完成」的键；丰富的 per-loop 运维数据不进语义事件日志，走 §4.3 的独立 metrics 流。

**DOER / CHECKER 分离**：自主循环的通用失效是让写代码的 agent 自己判「是否完成」——自述式 `<promise>` / `EXIT_SIGNAL` 易被「为逃出循环而撒谎」污染。本设计的 CHECKER 是**确定性门禁结果**：`sprint_complete` 仅在 reviewer 子代理对全部任务卡真返回 code-review `approved` 后由 orchestrator emit，不由 building agent 自评。这比自由文本自述、乃至「独立模型判 done」都更强——完成信号锚定真实质量门禁，而非任何 LLM 的判断。

### 3.4 熔断：stagnation circuit breaker

无人值守过夜的首要风险是某张任务卡反复失败把 token 烧到天亮。熔断分三级，阈值见 §4.1：

1. **卡级熔断** —— 同一任务卡累计 `needs_revision` 达 `UNATTENDED_CARD_REVISION_CEILING`：orchestrator 标该卡 `blocked` 并 emit `circuit_open`，跳下一张可并行卡。此为 headless 模式**新增**的「自动 blocked 跳卡」分支（见 §3.5、U-3），不是复用 §TDD Blocked Recovery 的「请求人工」终点；无人值守下 needs_revision 计数语义由 `UNATTENDED_CARD_REVISION_CEILING` 覆写既有「N≥2 请求人工」。
2. **循环级熔断** —— 连续 `UNATTENDED_STAGNATION_THRESHOLD` 轮**无进展**（`git HEAD` 未变 **且** 无新的 `agent_return status=completed` 事件）：外壳判定原地打转，emit `circuit_open` 并停止外循环。
3. **同错熔断** —— 连续 `UNATTENDED_SAME_ERROR_CEILING` 轮命中**同一错误签名**（失败根因指纹不变，即便 `git HEAD` 在变）：这是「在提交、但反复同一失败」的形态，无进展熔断（只看 HEAD）会漏判，故独立成一维。错误签名取自失败 agent-result 的归一化 root cause / 首个 traceback 帧，不含易变的路径行号。

`circuit_open` 事件行：

```json
{"ts":"2026-06-23T03:01:55+08:00","event":"circuit_open","phase":"development","agent":"orchestrator","ref":"dev-plan#T-014","detail":"stagnation: T-014 连续达 needs_revision 上限，标 blocked，停止外循环"}
```

熔断后外壳以非零退出，把决策权交还人工晨检——这与 Ralph「Ctrl+C + git reset 兜底」同构，但产出结构化事件而非中断信号。

### 3.5 与既有协议的衔接（背压复用，不另造）

- **背压 = 既有门禁**：每轮「一张卡完成」的判据是 tdd-engine GREEN 通过 + code-review `approved`，**完全复用**，外壳不重写质量逻辑。
- **续位 = Startup Protocol（headless 变体）**：每轮 fresh `claude -p` 后，orchestrator 按 AGENT.md §Startup Protocol 读 §项目状态 + dev-plan 自我定位到下一张 pending 卡。headless 下，Startup Protocol 中「占位符字段 → 向用户确认」一步须改为「跳过、视同已确认」，不得产生 `needs_input`；外壳 PROMPT 已显式注入 `${SPRINT}` 降低自我定位不确定性。
- **卡失败 = headless 新增分支**：U-3 在 ORCHESTRATOR-PROTOCOLS 为 headless 模式新增「自动标 `blocked` + 跳下一张可并行卡」分支——§TDD Blocked Recovery 原终点是「请求人工」，无人值守不可达，故新增而非复用。
- **headless 下的 needs_input**：无人应答，orchestrator 须把任何 `needs_input` 视同 `blocked`（emit `circuit_open`），不得自行假设——任务卡自足性由 §5 前置校验保证。

### 3.6 限流与用量限额处理

过夜无人值守必然撞 Claude 的调用速率与 5 小时用量限额。**撞限额是「等待」而非「无进展」**——若计入 stagnation 会误熔断、掩盖真实卡点。限额与熔断是正交轴：等待不消耗熔断预算，只有真实原地打转才消耗。

外壳按三层探测识别限额信号（层间为兜底关系，精确者优先）：

1. timeout guard —— 单轮 `claude -p` 超 `UNATTENDED_LOOP_ITER_TIMEOUT_SEC` 未返回即视为疑似阻塞。
2. 结构化 JSON —— `--output-format stream-json` 流中出现 `rate_limit` / usage-limit 事件字段（首选，精确）。
3. 过滤文本兜底 —— 仅当结构化信号缺失时匹配限额文本，且排除文件内容里「error / limit」字样的误报。

命中限额 → 外壳 **auto-wait**（读事件里的 reset 提示或退避到下一小时窗口）并**不递增 stagnation / same-error / iter 上限**计数，恢复后继续。速率侧以 `UNATTENDED_MAX_CALLS_PER_HOUR` 为软闸，接近上限即主动退避，避免把配额一次性烧空。

## 4. 规约

### 4.1 新增框架配置常量

并入 COMMON-RULES §框架配置常量（SSOT）。**禁止在脚本 / 协议中硬编码同一数值**，引用常量名。

| 常量名 | 值 | 说明 | 引用方 |
|--------|-----|------|--------|
| UNATTENDED_LOOP_MAX_ITERATIONS | 30 | 单次无人值守外循环对单 sprint 的迭代硬上限（runaway backstop） | unattended-building-loop |
| UNATTENDED_STAGNATION_THRESHOLD | 3 | 连续 N 轮无进展（git HEAD 未变 且 无新 `agent_return status=completed`）→ 循环级熔断 | unattended-building-loop |
| UNATTENDED_CARD_REVISION_CEILING | 3 | headless 下同一任务卡累计 `needs_revision` 达 N 次 → 标 `blocked` 跳过；比标准模式（§needs_revision 计数规范「N≥2 请求人工」）多一次重试，headless 无人应答故覆写其语义、不沿用「请求人工」 | orchestrator, unattended-building-loop |
| UNATTENDED_SAME_ERROR_CEILING | 5 | 连续 N 轮命中同一错误签名（root cause 指纹不变，即便 HEAD 在变）→ 同错熔断（§3.4-3） | orchestrator, unattended-building-loop |
| UNATTENDED_MAX_CALLS_PER_HOUR | 100 | 每小时 `claude -p` 调用软闸；接近即主动退避，防配额一次烧空（§3.6） | unattended-building-loop |
| UNATTENDED_LOOP_ITER_TIMEOUT_SEC | 1800 | 单轮无返回的疑似阻塞判据（限额三层探测第一层，§3.6） | unattended-building-loop |

### 4.2 EVENT-LOG schema 扩展

`EVENT_LOG_SCHEMA`（`.cataforge/schemas/event-log.schema.json`）的 `event` 枚举追加两个值；其余字段沿用现状（`ts` / `phase` / `detail` 必填，`agent` / `ref` 可选；`additionalProperties: false` 不破坏）。

```diff
       "enum": [
         "session_start",
         "session_end",
         ...
         "state_change",
         "correction",
-        "doc_finalize"
+        "doc_finalize",
+        "sprint_complete",
+        "circuit_open"
       ],
```

- `sprint_complete`：building 完成契约，外壳退出键，`ref=dev-plan#sprint-N`（§3.3）。
- `circuit_open`：熔断信号，`ref` 指向触发卡或 sprint（§3.4）。

per-loop 的 token / 耗时 / 文件变更等运维数据**不进**本 schema（语义事件日志不应被运维指标污染），走 §4.3。

### 4.3 运维 metrics 流（per-loop 可观测）

新增 `.cataforge/state/loop-metrics.jsonl`（运行时产物；U-2 在 `.cataforge/.gitignore` 追加 `state/`，与既有 `kg/store/` 约定对齐），每轮一行，供晨检「跑了几轮、烧了多少、哪卡卡住」：

```json
{"iter":7,"ts":"2026-06-23T02:14:07+08:00","sprint":"sprint-2","head_before":"a1b2c3d","head_after":"e4f5g6h","progressed":true,"files_changed":4,"tokens_in":18230,"tokens_out":5120,"duration_sec":612,"cards_total":6,"cards_done":5,"cards_blocked":0,"stagnation_count":0}
```

字段：`iter`/`ts`/`sprint`/`head_before`/`head_after`/`progressed`/`files_changed`/`tokens_in`/`tokens_out`/`duration_sec`/`cards_total`/`cards_done`/`cards_blocked`/`stagnation_count`。可选并入 `cataforge viz` 时间线（详见 [`visualization-integration.md`](visualization-integration.md) §A）做实时面板。

### 4.4 外循环脚本（参考实现）

`.cataforge/scripts/unattended/building-loop.sh`。常量值由 `cataforge` 注入或读自配置，脚本内不硬编码（下例以环境变量占位）。

```bash
#!/usr/bin/env bash
# 无人值守 building loop：对单个已冻结 sprint 反复拉起 orchestrator（fresh context）
# 直到 sprint_complete / circuit_open / 达迭代上限。只动 feature 分支，绝不 merge/deploy。
set -euo pipefail

SPRINT="${1:?用法: building-loop.sh <sprint-id> [max-iterations]}"
MAX="${2:-${UNATTENDED_LOOP_MAX_ITERATIONS:-30}}"
STAG_LIMIT="${UNATTENDED_STAGNATION_THRESHOLD:-3}"
CEILING="${UNATTENDED_CARD_REVISION_CEILING:-3}"
EVENT_LOG="docs/EVENT-LOG.jsonl"
METRICS=".cataforge/state/loop-metrics.jsonl"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"

# 轻量前置：分支非 main（完整冻结前置由 cataforge doctor 校验，U-5）
[ "$BRANCH" = "main" ] && { echo "拒绝：禁止在 main 上跑无人循环"; exit 2; }

# 基线：只认本次运行新追加的事件，避免历史 sprint_complete/circuit_open 误触发
baseline="$(wc -l < "$EVENT_LOG" 2>/dev/null || echo 0)"
new_events() { tail -n "+$((baseline + 1))" "$EVENT_LOG" 2>/dev/null; }

read -r -d '' PROMPT <<EOF || true
继续推进 ${SPRINT}（无人值守 building 模式）：
1. 按 Startup Protocol 读 §项目状态 + dev-plan 定位到 ${SPRINT} 下一张 pending 任务卡。
2. 经 tdd-engine 跑 TDD，GREEN 后调 code-review；approved 才算该卡完成，置 status=done 并 git commit 到当前 feature 分支。
3. 任一任务卡累计 needs_revision 达 ${CEILING} 次：标该卡 blocked，emit circuit_open，跳下一张可并行卡。
4. ${SPRINT} 全部任务卡 approved：emit sprint_complete（ref=dev-plan#${SPRINT}）。
约束：禁止 AskUserQuestion / 任何 needs_input（无人应答，遇到即视同 blocked + circuit_open）；
禁止 PR merge、禁止 deploy、禁止改 PRD/ARCH/DEV-PLAN（planning 留人工）。
EOF

iter=0
stagnation=0
while [ "$iter" -lt "$MAX" ]; do
  iter=$((iter + 1))
  head_before="$(git rev-parse HEAD)"
  events_before="$(wc -l < "$EVENT_LOG" 2>/dev/null || echo 0)"

  # 每轮 fresh context；沙盒内 skip-permissions 仅放行工具批准，不绕过 CataForge 门禁。
  # rc 捕获：claude 鉴权/超额类「无产出」非零退出不直接熔断，交由下方进展探测计入 stagnation。
  rc=0; claude -p "$PROMPT" --dangerously-skip-permissions --output-format stream-json --verbose || rc=$?
  [ "$rc" -ne 0 ] && echo "⚠ claude 非零退出 rc=${rc}（iter=${iter}），以进展探测判熔断。" >&2

  # 完成：本次运行内出现目标 sprint 的 sprint_complete（jq 精确字段匹配，杜绝 sprint-2 误匹配 sprint-20）
  if new_events | jq -e --arg s "dev-plan#${SPRINT}" 'select(.event=="sprint_complete" and .ref==$s)' >/dev/null 2>&1; then
    echo "✅ ${SPRINT} 完成（iter=${iter}），feature 分支待 PR，人工晨检后合并。"; exit 0
  fi
  # 熔断：本次运行内 orchestrator emit 的 circuit_open（卡级 ref 为任务卡，故不按 sprint 限定）
  if new_events | jq -e 'select(.event=="circuit_open")' >/dev/null 2>&1; then
    echo "⛔ 熔断（orchestrator emit circuit_open，iter=${iter}），停止，等待人工。"; exit 3
  fi

  # 进展探测：HEAD 变化 或 新增 completed agent_return
  head_after="$(git rev-parse HEAD)"
  events_after="$(wc -l < "$EVENT_LOG" 2>/dev/null || echo 0)"
  if [ "$head_after" != "$head_before" ] || [ "$events_after" -gt "$events_before" ]; then
    stagnation=0
  else
    stagnation=$((stagnation + 1))
  fi

  if [ "$stagnation" -ge "$STAG_LIMIT" ]; then
    cataforge event log --event circuit_open --phase development --agent orchestrator \
      --ref "dev-plan#${SPRINT}" --detail "stagnation: 连续 ${stagnation} 轮无进展，外壳熔断"
    echo "⛔ 熔断（stagnation=${stagnation}），停止，等待人工。"; exit 3
  fi
done

echo "⏹ 达迭代上限 MAX=${MAX}，${SPRINT} 未完成，停止，等待人工。"; exit 4
```

退出码：`0` 完成、`2` 前置校验失败、`3` 熔断、`4` 达上限。外壳串行（无并发抢分支），是相较「定时器并发拉起」更稳的形态。

## 5. 护栏与安全模型

| 护栏 | 规约 |
|------|------|
| 上游冻结前置 | `building-loop.sh` 做轻量前置（分支非 main）；`cataforge doctor` 做完整校验（已过 `pre_dev`、目标 sprint 依赖任务卡 AC 无 TBD；headless 无人答澄清，任务卡须自足；U-5 实现）。不满足则拒绝启动（exit 2）。 |
| skip-permissions ≠ 跳门禁 | `--dangerously-skip-permissions` 只放行 Claude Code 的**工具批准**，**不绕过** CataForge 的 code-review/doc-review 门禁（门禁在 orchestrator 内部，由 reviewer 子代理执行）。 |
| 沙盒隔离 | skip-permissions 必须在沙盒（容器 / 隔离工作树）内跑，最小权限、限网，与 Ralph 安全模型一致。 |
| 只动 feature 分支 | 禁止在 `main` 上跑（exit 2）；每轮 commit 到 feature 分支，**绝不自动 merge**。 |
| 保留 `pre_deploy` | `MANUAL_REVIEW_CHECKPOINTS` 的 `pre_deploy` 必须保留；无人循环只到「sprint building 完成 + PR 待审」，部署 go/no-go 永远人工。 |
| planning 留白天 | 无人循环禁止改 PRD/ARCH/DEV-PLAN；dev-plan 是 doc-review 冻结的质量锚，不可丢弃式重写。 |
| 护栏工具级强制 | merge / deploy / 改 PRD·ARCH·DEV-PLAN 的禁令不能只写在 PROMPT——自主 agent 可忽略它读不进心的 prompt 文本。由 **hook / 沙盒 deny 策略**在工具调用前确定性拦截：无人循环下 `git merge`、`git push origin main`、部署命令、planning 文件写入被阻断，PROMPT 文本降为二线提示。 |
| 自主提交身份 | 无人循环的 commit 用专属 git author（如 `cataforge-unattended <unattended@cataforge.local>`），晨检与事后审计据此区分自主提交与人工提交。 |
| 晨检交接 | 完成 / 熔断 / 达上限均产出结构化事件 + metrics；人工晨检 review PR、处理 `[ASSUMPTION]` 与 `blocked` 卡。 |

## 6. 决策记录

1. **为何自建 headless 外壳而非采用现成循环件**：任务图层——dev-plan 已是任务真相源，引入第二个任务管理器（prd.json 式）会双源打架，故不采用。循环驱动层有三个现成候选，均不契合「headless 沙盒 + 两态完成 + fresh-context」的过夜场景：
   - **官方 Ralph Wiggum 插件（Stop-hook，会话内）**：`--completion-promise` 精确串匹配**只能表达单条件**，无法区分 `sprint_complete` 与 `circuit_open` 两态；且会话内累积上下文，过夜长跑易 context-rot。
   - **原生 `/goal` + `/loop` + Routines**：交互 / 云端调度导向，非 headless `claude -p`；其 DOER/CHECKER 分离思想已被本设计以确定性事件契约吸收（§3.3）。可作**有人值守白天**的第二递送面，不覆盖沙盒过夜。
   - **frankbria/ralph-claude-code（外部 bash）**：形态最接近，其熔断成熟度（限流 / same-error / 5h 限额）已被 §3.4 / §3.6 吸收为参考基线；但其自述式 `EXIT_SIGNAL` 完成判据弱于本设计的门禁锚定事件契约。

   结论：缺口只在「外循环 + 熔断 + 完成契约」三样薄外壳，且须 headless + 两态 + fresh-context，故自建最小外壳、复用 orchestrator 与既有门禁。**重评估条件**：若 `/goal` 开放稳定 headless 接口，或需并行多 sprint 扇出，再评估采用原生件 / Agent SDK / Dynamic Workflows。
2. **为何完成判据用事件契约而非 LLM 自述**：Ralph 实践证明显式 `completion-promise` 比自由文本自述可靠；外壳须确定性退出，故定义 `sprint_complete` 事件。**备选**（已否决）：解析 orchestrator 末轮文本判完成——不稳定、易误退。
3. **为何运维 metrics 与语义 EVENT-LOG 分流**：`EVENT_LOG_SCHEMA` 是 `additionalProperties: false` 的语义审计源，掺入 token/耗时会污染其语义并破坏 schema；故 per-loop 运维数据走独立 gitignore 的 `loop-metrics.jsonl`。
4. **为何限定 development 阶段 building**：planning 信息密度高、需人类判断，且 dev-plan 是质量锚不可丢弃；Ralph 哲学只适配 building/已冻结场景。这与执行模式矩阵的 `agile-prototype`↔`standard` 光谱一致。**重评估条件**：若未来 doc-review 能在 headless 下稳定守门 planning 产出，再评估扩展。

## 7. 缺口分解与 PR 序列

| 序号 | 主题 | 核心内容 | 依赖 |
|------|------|---------|------|
| U-1 | 事件契约 + 常量 | ① `.cataforge/schemas/event-log.schema.json` 的 `event` 枚举追加 `sprint_complete` / `circuit_open`；② **同步**更新 `src/cataforge/core/event_log.py` 的 `VALID_EVENTS`（两处不一致则 `run_local.py` 的 schema↔mirror parity 守卫 FAIL）；③ COMMON-RULES §框架配置常量 加 §4.1 全部常量（含 same-error / 限流 / 迭代超时）；④ orchestrator 全卡 approved 时 emit `sprint_complete`、卡级熔断时 emit `circuit_open` | 无 |
| U-2 | 外循环脚本 | `building-loop.sh` 参考实现 + 前置校验 + 退出码；`.cataforge/state/` gitignore | U-1 |
| U-3 | 熔断与限额 | TDD Blocked Recovery 增「自动 blocked」分支（替换 headless 下的人工触发）；`UNATTENDED_CARD_REVISION_CEILING` 接入 needs_revision 计数；same-error 熔断（`UNATTENDED_SAME_ERROR_CEILING`，§3.4-3）；§3.6 限流 / 5h 用量限额三层探测 + auto-wait（不计入熔断预算） | U-1 |
| U-4 | 运维 metrics | `loop-metrics.jsonl` 写入器 + schema；可选并入 `cataforge viz` 时间线 | U-2 |
| U-5 | 文档与守卫 | COMMON-RULES / ORCHESTRATOR-PROTOCOLS 措辞收口；`cataforge doctor` 校验无人循环前置条件；merge/deploy/planning 禁令的 hook / 沙盒 deny 强制层（§5）；自主提交 git 身份；agile-prototype 模式接线 | U-1~U-4 |

并行性：U-1 是其余全部的前置；U-2 ⊥ U-3 可并行（均依赖 U-1）；U-4 依赖 U-2；U-5 收尾。

## 8. 验收标准

1. 在一个已过 `pre_dev`、dev-plan 经 doc-review 冻结的 standard 项目上，对某 sprint 跑 `building-loop.sh <sprint>`：无人值守完成全部任务卡的 TDD + code-review，每卡 commit 到 feature 分支，末轮 emit `sprint_complete`，外壳 exit 0，全程零 `AskUserQuestion`。
2. 构造一张「故意无法 GREEN」的任务卡：连续达 `UNATTENDED_CARD_REVISION_CEILING` 后该卡被标 `blocked`，emit `circuit_open`，外壳 exit 3，其余可并行卡不受影响。
3. 构造「连续 N 轮无进展」场景：外壳在 `UNATTENDED_STAGNATION_THRESHOLD` 轮后熔断 exit 3。
4. 全程不触碰 `main`、不 merge、不 deploy、不改 PRD/ARCH/DEV-PLAN；`loop-metrics.jsonl` 每轮一行，字段完整；`EVENT-LOG.jsonl` 通过 `EVENT_LOG_SCHEMA` 校验，且 schema 与 `event_log.py` 镜像通过 `run_local.py` 的 schema↔mirror parity 守卫。
5. `cataforge doctor` 在缺少上游冻结前置时拒绝启动（exit 2）（净新增能力，依赖 U-5 实现）。
6. 撞速率 / 5h 用量限额时外壳 auto-wait 并恢复，且该等待不递增 stagnation / same-error / iter 计数（构造限额响应验证，§3.6）。
7. 构造「HEAD 在变但反复同一错误签名」场景：达 `UNATTENDED_SAME_ERROR_CEILING` 轮后 same-error 熔断 exit 3（§3.4-3）。
8. PROMPT 被注入 `git push origin main` / 部署 / 改 dev-plan 类指令时，被 hook / 沙盒 deny 层拦截，非仅靠 PROMPT 文本约束（§5）。
