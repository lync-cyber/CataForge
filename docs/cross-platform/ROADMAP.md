# CataForge 跨平台演进路线图

> 基于 foamy-tumbling-curry.md（v2 方案）+ 代码库实态分析 + 目录结构重构决策生成。
> 设计决策已确认，可直接作为跨会话执行蓝图。

## 设计决策记录

| # | 决策点 | 结论 |
|---|--------|------|
| D-1 | 规范格式中的工具名 | **引入能力标识符**（`file_read`, `shell_exec`, `agent_dispatch` 等） |
| D-2 | runtime 包语言 | **全 Python 实现** |
| D-3 | framework.json 版本策略 | `runtime_api_version` 作为**独立字段** |
| D-4 | Cursor tool_map | 基于**实际 API** 纠正（Cursor 有独立 Read/Write/StrReplace/Glob/Grep/Shell） |
| D-5 | Hook _hook_base.py | **统一 stdin 解析**层 |
| D-6 | 向后兼容 | Phase 1 完成后**不要求**向后兼容 |
| D-7 | 目录结构 | **`.cataforge/`** 为框架核心（平台无关）；**`.claude/`** 仅含平台配置 + 同步链接 |

## Phase 概览

```
Phase 0: 目录结构重构                    ████████░░░░░░░░░░░░  (3-5 天)
  └─ .claude/ → .cataforge/ 迁移 + platform_sync.py

Phase 1: 最小抽象提取                    ░░░░░░░░░░░░░░░░░░░░  (1-2 周)
  ├─ 1.1 建立 .cataforge/runtime/ 包骨架
  ├─ 1.2 framework.json 扩展
  ├─ 1.3 result_parser 提取
  ├─ 1.4 agent-dispatch SKILL.md 拆分
  ├─ 1.5 tdd-engine SKILL.md 平台无关化
  └─ 1.6 能力标识符迁移

Phase 2: 平台适配器                      ░░░░░░░░░░░░░░░░░░░░  (2-3 周)
  ├─ 2.1 OpenCode 适配器 (P0)
  ├─ 2.2 Cursor 适配器 (P1)
  └─ 2.3 Codex CLI 适配器 (P2)

Phase 3: Hook 桥接层                     ░░░░░░░░░░░░░░░░░░░░  (1 周)
  ├─ 3.1 _hook_base.py 统一解析层
  ├─ 3.2 Hook 脚本工具名去硬编码
  └─ 3.3 平台 Hook 配置生成器

Phase 4: 端到端验证与 API 稳定化          ░░░░░░░░░░░░░░░░░░░░  (1 周)
  ├─ 4.1 适配器合规测试
  ├─ 4.2 Bootstrap 平台选择
  └─ 4.3 API 版本锁定
```

## 目录结构对比

```
迁移前                              迁移后
─────────                           ─────────
.claude/                            .cataforge/              ← 框架核心 (平台无关)
├── framework.json                  ├── framework.json
├── settings.json  ─────────────┐   ├── runtime/             ← Phase 1 新建
├── agents/                     │   ├── agents/
├── skills/                     │   ├── skills/
├── rules/                      │   ├── rules/
├── schemas/                    │   ├── schemas/
├── scripts/                    │   ├── scripts/
├── hooks/                      │   ├── hooks/
└── integrations/               │   └── integrations/
                                │
                                │   .claude/                 ← 平台适配 (瘦壳)
                                └── ├── settings.json        ← 仅此文件手动维护
                                    ├── agents/ → link       ← platform_sync 生成
                                    └── rules/ → link        ← platform_sync 生成
```

## 文件变更全景

### Phase 0 变更（目录重构）

| 操作 | 数量 | 说明 |
|:----:|:----:|------|
| 移动 | 87 | `.claude/` → `.cataforge/` |
| 新增 | 1 | `platform_sync.py` |
| 修改 | ~40 | 路径引用更新 |
| 快照更新 | ~19 | tests/snapshots/ |

### Phase 1-4 新增文件（26 个，路径均在 `.cataforge/`）

| Phase | 文件路径 | 用途 |
|:-----:|----------|------|
| 1 | `.cataforge/runtime/__init__.py` | 包初始化 |
| 1 | `.cataforge/runtime/types.py` | DispatchRequest, AgentResult, AgentStatus, Capability |
| 1 | `.cataforge/runtime/interfaces.py` | 5 个抽象基类 |
| 1 | `.cataforge/runtime/result_parser.py` | 4 级容错解析器 |
| 1 | `.cataforge/runtime/tool_map.yaml` | 能力标识符 → 平台工具名 |
| 1 | `.cataforge/runtime/adapters/__init__.py` | 适配器包 |
| 1 | `.cataforge/runtime/adapters/_registry.py` | 平台检测 + 工厂 |
| 1 | `.cataforge/runtime/adapters/claude_code.py` | Claude Code 适配器 |
| 2 | `.cataforge/runtime/adapters/opencode.py` | OpenCode 适配器 |
| 2 | `.cataforge/runtime/adapters/cursor.py` | Cursor 调度适配器 |
| 2 | `.cataforge/runtime/adapters/cursor_hooks.py` | Cursor Hook 映射 |
| 2 | `.cataforge/runtime/adapters/cursor_rules_gen.py` | .cursor/rules/ 生成器 |
| 2 | `.cataforge/runtime/adapters/codex.py` | Codex 调度适配器 |
| 2 | `.cataforge/runtime/adapters/codex_definition.py` | YAML→TOML 转换器 |
| 2 | `.cataforge/runtime/adapters/codex_hooks.py` | Codex Hook 映射 |
| 3 | `.cataforge/runtime/hook_bridge.py` | HookBridge 基础实现 |
| 4 | `tests/test_runtime/` (6 files) | 测试套件 |
| 4 | `.cataforge/runtime/adapters/_conformance.py` | 适配器合规检查 |

### Phase 1-4 修改文件（路径已修正为 `.cataforge/`）

| Phase | 文件路径 | 变更摘要 |
|:-----:|----------|----------|
| 1 | `.cataforge/framework.json` | `runtime` + `runtime_api_version` 字段 |
| 1 | `.cataforge/skills/agent-dispatch/SKILL.md` | 平台无关化 |
| 1 | `.cataforge/skills/agent-dispatch/templates/dispatch-prompt.md` | 模板格式 |
| 1 | `.cataforge/skills/tdd-engine/SKILL.md` | 8 处去硬编码 |
| 1 | `CLAUDE.md` | 运行时字段 |
| 1 | 13× `.cataforge/agents/*/AGENT.md` | 能力标识符迁移 |
| 3 | `.cataforge/hooks/_hook_base.py` | 统一解析 + 平台检测 |
| 3 | `.cataforge/hooks/` (6 scripts) | 工具名去硬编码 |
| 4 | `.cataforge/scripts/framework/setup.py` | `--platform` 参数 |
| 4 | `.cataforge/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md` | 平台选择步骤 |
| 4 | `pyproject.toml` | 版本号 |

## 依赖关系

```
Phase 0 ─────────► Phase 1 ─────────┐
 (目录重构)         (runtime 包)      ├──► Phase 2 (适配器)
                                     │       │
                                     │       ├──► Phase 3 (Hook 桥接)
                                     │       │
                                     │       └──► Phase 4 (验证)
                                     │
                                     └──► Phase 3 (可部分并行)
```

## 跨会话执行指南

每个 Phase 对应独立文档（`phase-N-*.md`），包含精确到行号的变更、Python 代码草案和验收标准。

会话恢复时: 读取 ROADMAP.md → 确认上次完成的 Phase → 读取下一个 phase 文档 → 继续执行。

### 检查点命令

```bash
# Phase 0 完成检查
python .cataforge/scripts/framework/platform_sync.py --check

# Phase 1-4 完成检查
python .cataforge/runtime/adapters/_conformance.py --platform claude-code
```
