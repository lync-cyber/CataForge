# Orchestrator Meta Protocols

> 框架元运维与学习协议 — 低频触发、reference 性质，不进入每次阶段决策的热路径。

---

## Framework Upgrade Protocol
框架升级时保持项目状态不变:

### 可安全覆盖（框架文件）
- .cataforge/agents/ — 所有 AGENT.md
- .cataforge/skills/ — 所有 SKILL.md + templates/ + scripts/
- .cataforge/rules/ — COMMON-RULES.md, SUB-AGENT-PROTOCOLS.md
- .cataforge/agents/orchestrator/ — ORCHESTRATOR-PROTOCOLS.md, ORCHESTRATOR-META-PROTOCOLS.md
- .cataforge/hooks/ — 所有 Hook 脚本 (.py)
- .cataforge/scripts/framework/ — `setup.py`（环境探测/平台配置）、`event_logger.py`（`cataforge event log` 的路径稳定 shim，供 markdown 协议调用）；其他框架能力（upgrade、docs load/index 等）已上收为 `cataforge` CLI 子命令；Penpot 集成无需 scaffold 落盘脚本，全部通过 `cataforge penpot {deploy|mcp-only|start|stop|status|ensure}` 子命令暴露（实现位于 `cataforge.adapter.integrations.penpot`）
- .cataforge/framework.json
- pyproject.toml

### 绝不触碰（项目数据）
- {INSTRUCTION_FILE} 的 "项目状态" 段
- docs/ 目录下所有文档
- src/ 目录下所有代码
- .cataforge/learnings/ 下的经验文件

### 需要合并（混合文件）
- 平台配置文件（Claude: `.claude/settings.json` / `.mcp.json`；Cursor: `.cursor/hooks.json` / `.cursor/mcp.json`）— 保留项目 env、自定义 permissions、MCP 配置
- .cataforge/framework.json — upgrade.source 保留用户已配置的 repo/url，仅补充新字段；upgrade.state 为项目本地升级状态，始终保留；features 和 migration_checks 为框架出厂配置，全量覆盖
- {INSTRUCTION_FILE} 全局约定 — 保留用户已填写的值，新增框架默认字段

### 初始化安装
- 运行: `cataforge setup` 检测环境并安装依赖
- 可选 Penpot: `cataforge setup --with-penpot`
- 仅检测: `cataforge setup --check-prereqs`

### 升级步骤（本地路径方式）
适用场景：想用一个本地 CataForge 仓库的 checkout 升级，而不是从 PyPI/远程安装。
1. 安装目标版本到当前环境: `pip install <新版CataForge路径>`（或 `uv tool install <路径>`）
2. 运行: `cataforge upgrade apply --dry-run` 预览变更
3. 确认变更列表无异常
4. 运行: `cataforge upgrade apply` 执行升级（scaffold 刷新；用户状态保留）
5. 运行: `cataforge upgrade verify` 执行升级后验证（= `cataforge doctor`）
6. 检查: `git diff .cataforge/` 确认变更合理
7. 提交: `git commit -m "chore: upgrade CataForge framework to vX.Y.Z"`

### 升级步骤（PyPI/远程方式）
1. 升级包: `pip install --upgrade cataforge`（或 `uv tool upgrade cataforge`）
2. 运行: `cataforge upgrade check` 对比已安装包版本与 scaffold 版本
3. 运行: `cataforge upgrade apply --dry-run` 预览变更
4. 运行: `cataforge upgrade apply` 执行 scaffold 刷新
5. 检查: `git diff .cataforge/` 确认变更合理
6. 提交: `git commit -m "chore: upgrade CataForge framework to vX.Y.Z"`

### 独立验证
- 运行: `cataforge upgrade verify` 可随时检查框架文件完整性

---

## Event Log 规范
orchestrator 在关键节点向 `docs/EVENT-LOG.jsonl` 追加事件记录，用于审计追踪和 reflector 回顾分析。

**格式**: JSONL（每行一个 JSON 对象），Schema 见 `.cataforge/schemas/event-log.schema.json`
- 必填字段: `ts` (ISO 8601), `event`, `phase`, `detail`
- 可选字段: `agent`, `task_type`, `status`, `ref`

**事件类型与写入时机**:
| 事件 | 触发条件 | 写入方式 |
|------|---------|---------|
| session_start | 会话启动 | **Hook 自动** (session_context.py，含 60 秒 compact 去重；仅此一个事件由 hook 写入，orchestrator 不再手动补写以节省 token) |
| agent_dispatch | 调度子代理前 | **Hook 自动** (log_agent_dispatch.py, PreToolUse Agent) |
| agent_return | 子代理返回结果后 | **Hook 自动** (validate_agent_result.py, PostToolUse Agent) |
| phase_start | Phase Transition Protocol 步骤 5 | **[EVENT]** orchestrator 手动 |
| phase_end | reviewer 返回 approved | **[EVENT]** orchestrator 手动 |
| review_verdict | reviewer 返回审查结论 | **[EVENT]** orchestrator 手动 |
| user_decision | 用户在 Approved-with-Notes / Change Request 中做出选择 | **[EVENT]** orchestrator 手动 |
| revision_start | 进入 Revision Protocol | **[EVENT]** orchestrator 手动 |
| tdd_phase | TDD RED/GREEN/REFACTOR 阶段切换 | **[EVENT]** tdd-engine skill 步骤内嵌 |
| state_change | {INSTRUCTION_FILE} 状态字段变更 | **[EVENT]** orchestrator 手动 |
| doc_finalize | context finalize 完成 | **[EVENT]** context skill 步骤内嵌 |
| incident | 崩溃、rolled-back 等异常事件 | **[EVENT]** orchestrator 手动 |
| correction | On-Correction Learning 触发时 | **[EVENT]** orchestrator 手动 |

**写入方式**:
- **Hook 自动**: 由 `.cataforge/hooks/` 中的 hook 脚本自动触发，无需 orchestrator 记忆
- **[EVENT] 手动**: 使用 `cataforge event log` CLI，已嵌入各协议步骤中（标记为 **[EVENT]**）

**禁止旁路** ⚠️：
- 严禁直接 `echo '{...}' >> docs/EVENT-LOG.jsonl` 或 `cat <<EOF >> ...` 等 shell 重定向写入。`cataforge event log` 是唯一会跑 schema 校验的入口；旁路写入会导致 `unknown field`（如 `timestamp` ≠ `ts`）或 `non-enum event`（如 `doc_revision_completed` ≠ `revision_completed`）滑过门禁，被 reflector 消费时才暴露。
- 若发现某个事件类型在枚举中缺失，应该向 `.cataforge/schemas/event-log.schema.json` + `cataforge.core.event_log.VALID_EVENTS` 同时添加（见 §schema 同步），而不是临时绕开 CLI。
- `cataforge doctor` 的 "EVENT-LOG schema sample" 与 "EVENT-LOG bypass guard" 段会捕获这两类违规并在 CI 中失败。

```bash
cataforge event log --event phase_start --phase architecture --detail "进入架构设计阶段"
```

---

## On-Correction Learning Protocol

**触发条件** (任一命中即记录):
| 信号 | 数据来源 | 执行者 | 严重度 |
|---|---|---|---|
| option-override | AskUserQuestion 用户选项 ≠ `(Recommended)` | hook `detect_correction.py` | hard |
| interrupt-override | Interrupt-Resume 中用户回答推翻 agent `[ASSUMPTION]` | orchestrator (via `cataforge correction record`) | hard |
| review-flag | reviewer 将 `[ASSUMPTION]` 条目判为 CRITICAL/HIGH | hook `detect_review_flag.py` | review |

**写入规则**:
- hook / reviewer 命中时自动 append 到 `docs/EVENT-LOG.jsonl` (event=correction) + `docs/reviews/CORRECTIONS-LOG.md`（格式: date | agent | phase + 触发信号 + 问题/假设 + 基线 + 实际 + 偏差类型）
- 所有路径（hook / CLI）共享 `cataforge.core.corrections.record_correction` 作为唯一写入口，双日志保持同步；orchestrator 勿绕过 CLI 直接手写 EVENT-LOG（会导致 CORRECTIONS-LOG 漏写）
- interrupt-override 时 orchestrator 必须调用：
  ```bash
  cataforge correction record \
    --trigger interrupt-override \
    --agent {被推翻的 agent} --phase {phase} \
    --question "{被推翻的 [ASSUMPTION] 原文}" \
    --baseline "{agent 假设}" --actual "{用户纠正}" \
    --deviation self-caused
  ```
- CORRECTIONS-LOG.md 为追加写入，不覆盖
- 运维诊断：`cataforge doctor` 的 "Hook script importability" 段会在每次启动时校验 hook 模块可导入；失败即表示 option-override / review-flag 通路失效（静默），需 `pip install -e .` 或重装 wheel 修复

**消费**: reflector 在 Retrospective & Improvement 中将该文件作为输入源；仅 `hard` 和 `review` 条目计入 `RETRO_TRIGGER_SELF_CAUSED` 阈值，`soft` 仅用于 Adaptive Review 聚合统计。

---

## Adaptive Review Protocol
执行者: orchestrator 自身（不启动子代理）

### 收紧分支（默认）
触发条件: 任一文档达到 needs_revision(N>=2)
步骤:
1. 扫描 docs/reviews/doc/ 和 docs/reviews/code/ 下当前阶段的 REVIEW 文件（含 -r{N} 归档版本），提取 root_cause=self-caused 的问题按 category 聚合
2. 同一 category >=2 次 → 在下次 agent-dispatch 调度同一 Agent 时注入临时提示：
   ```
   === 本项目已识别的反复问题 ===
   - {category}: {问题描述}，已出现{N}次
   ```

### 反向降级分支
触发条件: 连续 `ADAPTIVE_REVIEW_DOWNGRADE_CLEAN_TASKS` 个 TDD 任务（默认 10）满足以下全部条件，视为项目质量已稳态：
- code-review verdict 为 approved（无 MEDIUM/HIGH/CRITICAL）
- 对应任务 CORRECTIONS-LOG.md 无新增 hard / review 条目
- 该 Agent 在该阶段近期无 needs_revision

降级动作（持续到下一次任一上述条件失败时取消）:
1. 在 {INSTRUCTION_FILE} `Learnings Registry` 字段写入 `adaptive-review downgraded for {phase}: layer1-only`
2. 后续该阶段 code-review 调用追加 `--layer1-only` 标记，跳过 Layer 2 AI 语义审查（仅 lint + 腐化探针），sprint-review 仍按原规则执行作为兜底
3. **[EVENT]** 记录降级事件:
   ```bash
   cataforge event log --event review_verdict --phase {当前阶段} --agent orchestrator --status approved --detail "adaptive-review downgraded — {N} consecutive clean tasks"
   ```
4. 任一后续任务 code-review 出现 MEDIUM+ 问题或 CORRECTIONS-LOG 写入新 hard 条目 → 立即取消降级，恢复完整 Layer 2 审查并清空"连续 clean"计数

降级是项目级状态，不是 Agent 级别；切阶段（Phase 5 → 6）自动重置。

---

## Retrospective & Improvement Protocol
触发条件: 所有 Phase 完成后执行一次（不阻塞项目交付）

**执行模式: inline** —— 与 change-guard / Adaptive Review 一致，orchestrator 直接执行 reflector AGENT.md §Retrospective Protocol；reflector 的 `inline_dispatch: true` frontmatter 即此 hint。

步骤:
1. **触发门槛判定**: 满足以下任一条件才触发 retrospective，否则跳过:
   - `docs/reviews/CORRECTIONS-LOG.md` 中 `偏差类型` 累计命中 self-caused 的条目数 ≥ `RETRO_TRIGGER_SELF_CAUSED`，或
   - 本项目任一 REVIEW / CODE-REVIEW / CODE-SCAN / FRAMEWORK-REVIEW 报告包含 CRITICAL 级别问题
   跳过时在 {INSTRUCTION_FILE} `Learnings Registry` 字段记录 `retro skipped (below threshold)` 并**[EVENT]** 写入 `review_verdict`（agent=reflector, status=approved, detail="retro skipped (below threshold)"）
2. **执行 reflector §Retrospective Protocol**: orchestrator 自行加载 `{AGENTS_SRC_DIR}/reflector/AGENT.md` §Retrospective Protocol（含 EVENT-LOG.jsonl 扫描），按其步骤 1-7 完成产出
3. 产出文件:
   - docs/reviews/retro/RETRO-{project}-{cycle}.md（`{cycle}` = sprint 编号或迭代标签，仅 slug；版本号写入 frontmatter `version:`，含 EXP 经验条目）
   - docs/reviews/retro/SKILL-IMPROVE-{skill_id}.md（含每条 EXP 对应的具体 Agent/Skill 文件修改建议）
4. orchestrator 向用户展示 RETRO 报告中的经验条目和改进建议
5. 用户审批后执行修改，git commit，message 格式: `learn: apply EXP-{NNN} to {target_file}`
6. reflector 协议遇到不可恢复错误（docs/reviews/ 子目录不存在或全空、EVENT-LOG.jsonl 解析失败）时仅记录 `incident` 事件，不影响项目完成状态
7. **fallback to subagent**: 主对话上下文饱和或用户显式偏好独立 retro 报告时，降级使用 `cataforge agent run reflector --task-type retrospective`；这是逃生通道，不是默认路径
