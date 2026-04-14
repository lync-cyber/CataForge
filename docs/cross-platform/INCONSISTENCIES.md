# 方案演进记录：v1 → v2

> v1 = 原始方案（foamy-tumbling-curry.md + 首版 Phase 0-4）
> v2 = 重构方案（本目录下当前 ROADMAP.md + Phase 0-5）
> 本文档记录 v1 中发现的问题及 v2 的解决方式。

---

## v1 问题清单与 v2 处置

### P-1: Override 机制缺失（决策 D-2 未实现）

- **严重度**: CRITICAL
- **v1 问题**: v1 将 `dispatch-prompt.md` 中的 Claude Code 专有文字替换为通用文字（如 `Agent tool:` → `调度请求:`），但未建立 override 文件和合并机制。所有平台收到完全相同的 prompt，无法适配平台差异（如 Codex 的异步两步调度、上下文窗口限制）。
- **v2 解决**: Phase 1 Step 1.2 建立完整的段落级 Override 机制：
  - 基础模板含 5 个 `<!-- OVERRIDE:name -->` 标记点
  - 各平台 override 文件（`platforms/{id}/overrides/dispatch-prompt.md`）仅提供差异段落
  - `template_renderer.py` 负责合并
- **状态**: ✅ 已在 v2 Phase 1 中设计

### P-2: PROJECT-STATE.md 缺失（决策 D-4 未实现）

- **严重度**: CRITICAL
- **v1 问题**: 继续以 `CLAUDE.md` 作为项目状态载体，未引入平台无关的 `PROJECT-STATE.md`。
- **v2 解决**: Phase 1 Step 1.3 引入 `PROJECT-STATE.md`，Phase 2 Step 2.4 从 `CLAUDE.md` 提取生成。deploy 负责 `PROJECT-STATE.md` → `CLAUDE.md` 同步。
- **状态**: ✅ 已在 v2 Phase 1-2 中设计

### P-3: Dispatcher 接口空壳（设计实践）

- **严重度**: HIGH
- **v1 问题**: 4 个 Dispatcher 的 `dispatch()` 方法均 `raise NotImplementedError`，注释承认"不会被 Python 调用"。产生 26 个新文件但可执行价值极低。
- **v2 解决**: 取消抽象接口。改为声明式 `profile.yaml`（D-7）+ 可执行工具层（`profile_loader`、`template_renderer`、`frontmatter_translator`、`hook_bridge`、`deploy`）。
- **状态**: ✅ 已在 v2 Phase 1 中重新设计

### P-4: 工具名映射双源（设计实践）

- **严重度**: HIGH
- **v1 问题**: `tool_map.yaml` 和 `_hook_base.py` 内联字典维护各自的映射表，更新时易不一致。
- **v2 解决**: 统一到 `profile.yaml` 单源。`_hook_base.py` 运行时从 `profile.yaml` 加载（带缓存和 fallback）。
- **状态**: ✅ 已在 v2 Phase 4 中设计

### P-5: 能力标识符致命风险

- **严重度**: CRITICAL
- **v1 问题**: 直接替换 AGENT.md 的 `tools: Read, Write` 为 `tools: file_read, file_write`。Claude Code 不识别自定义能力标识符，会导致子代理工具权限异常。v1 仅在风险项中提及缓解方案，未纳入正式设计。
- **v2 解决**: 源/产物分离。源 AGENT.md（`.cataforge/agents/`）使用能力标识符，deploy 翻译为原生名后写入部署目录（`.claude/agents/`）。Claude Code 永远只看到原生名，零风险。
- **状态**: ✅ 已在 v2 Phase 2 Step 2.2 中设计

### P-6: settings.json 规范源矛盾（决策 D-1 违反）

- **严重度**: MEDIUM
- **v1 问题**: Phase 3 将 `.claude/settings.json` 作为 Hook 的"规范源"，由 `hook_bridge` 从中翻译。但 D-1 要求源定义在 `.cataforge/`。
- **v2 解决**: 引入 `.cataforge/hooks/hooks.yaml` 作为 Hook 规范源定义（Phase 1 Step 1.4）。deploy 从 hooks.yaml + profile 生成各平台配置。`.claude/settings.json` 仅为 Claude Code 的平台配置文件。
- **状态**: ✅ 已在 v2 Phase 1 + Phase 4 中设计

### P-7: deploy 自动化缺失（决策 D-1 权衡未实施）

- **严重度**: MEDIUM
- **v1 问题**: `platform_sync.py` 仅为手动 CLI，无自动化触发。D-1 明确提到"可通过 SessionStart hook 或 git hook 自动化"缓解增加的 deploy 步骤。
- **v2 解决**: Phase 4 中 `session_context.py` 增强，在 SessionStart 时自动调用 deploy 同步。
- **状态**: ✅ 已在 v2 Phase 4 Step 4.2 中设计

### P-8: 执行策略风险（先重构后验证）

- **严重度**: HIGH
- **v1 问题**: Phase 0 前置 87 文件迁移（最大工作量），Phase 1 新建 26 个文件，在任何平台验证之前。如果核心假设（如 Cursor Agent 加载机制）不成立，大量工作需返工。
- **v2 解决**: Phase 0 改为 Cursor 最小验证（3-5 天，不动文件结构），用验证结论指导后续设计。
- **状态**: ✅ 已在 v2 Phase 0 中设计

### P-9: Phase 4 测试路径错误（内部不一致）

- **严重度**: LOW
- **v1 问题**: Phase 4 测试代码中 `sys.path.insert(0, ... / ".claude")` 指向旧目录，与 Phase 0 的 `.cataforge/` 迁移矛盾。
- **v2 解决**: Phase 5 测试统一使用 `.cataforge/` 路径。
- **状态**: ✅ 已在 v2 Phase 5 中修正

### P-10: 退化策略缺乏具体实现

- **严重度**: MEDIUM
- **v1 问题**: `hook_bridge.py` 的覆盖矩阵标注了 "degraded"，但具体如何退化（rules 注入？prompt checklist？）没有设计。
- **v2 解决**: `hooks.yaml` 中定义 `degradation_templates`，`hook_bridge.apply_degradation()` 按策略具体化为文件变更（rules 注入、prompt checklist 等）。
- **状态**: ✅ 已在 v2 Phase 1 Step 1.4 + Phase 4 Step 4.3 中设计

---

## v1 CONFIRMED 项（仍然有效）

以下 v1 分析结论在 v2 中保持有效：

| # | 内容 | 状态 |
|---|------|------|
| C-1 | Agent 和 Skill 数量（13 + 22） | 有效 |
| C-2 | agent-dispatch/SKILL.md:74 硬编码 claude-code | 有效（v2 Phase 2 修改） |
| C-3 | agent-dispatch/SKILL.md:38-44 调度实现段落 | 有效（v2 Phase 2 修改） |
| C-4 | tdd-engine/SKILL.md 架构图 | 有效（v2 Phase 2 修改） |
| C-5 | settings.json hooks 段落位置 | 有效（不再作为规范源） |

## v1 INCONSISTENT 项处置状态

| # | v1 问题 | v2 处置 |
|---|--------|--------|
| I-1 | 遗漏 ORCHESTRATOR-PROTOCOLS.md | v2 Phase 5 Step 5.2 覆盖 |
| I-2 | setup.py --apply-permissions | v2 Phase 5 setup.py --platform |
| I-3 | Cursor tool_map 映射错误 | v2 Phase 1 profile.yaml 基于实际 API 纠正 |
| I-4 | _hook_base.py 跨平台适配 | v2 Phase 4 Step 4.1 完整设计 |
| I-5 | AGENT.md tools 处理策略 | v2 Phase 2 能力标识符 + deploy 翻译 |
| I-6 | Cursor rules 评估简化 | v2 Phase 3 Step 3.2 MDC 生成 |
| I-7 | 目录结构解耦 | v2 Phase 2 .cataforge/ 完整迁移 |

---

## 版本号语义（不变）

| 位置 | 字段 | 当前值 | v2 目标值 | 语义 |
|------|------|--------|----------|------|
| pyproject.toml | `[project].version` | `0.9.13` | `0.10.0` | CataForge 发行版本 |
| framework.json | `version` | `0.3.0` | `0.3.0` | 框架配置 schema 版本 |
| framework.json | `runtime_api_version` | (新增) | `1.0` | 运行时接口 API 版本 |

---

## 总结

| 分类 | 数量 |
|------|------|
| v1 问题（v2 已解决） | 10/10 |
| v1 CONFIRMED（仍有效） | 5 |
| v1 INCONSISTENT（v2 已覆盖） | 7/7 |
| v2 新增设计决策 | 3 (D-5 能力标识符、D-6 先验证、D-7 工具层定位) |
