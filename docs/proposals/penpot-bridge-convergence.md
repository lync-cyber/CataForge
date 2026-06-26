# 提案：Penpot 集成收敛为 penpot-bridge 单能力 + 权威划分重构

> 状态：待实施（多 PR，按依赖序）。
> 范围：`.cataforge/skills/penpot-*`、`.cataforge/skills/context`（ui-spec 模板）、`ui-designer`/`implementer`/`reviewer` 三 AGENT.md、`framework.json` features、`ORCHESTRATOR-PROTOCOLS.md`；PR-C2/PR-E 触及 `src/cataforge/adapter/integrations/penpot` 与 `cataforge.context` backend。
> 依据：[FRAMEWORK-REVIEW-penpot-ui-flow-20260626-r1](../reviews/framework/FRAMEWORK-REVIEW-penpot-ui-flow-20260626-r1.md)（R-001~R-007）。
> 交付边界：本文为施工蓝图与验收标准；落地以各 PR 的 git diff 为准。**不含工时估算**，仅依赖序与优先级。

---

## 0. 根因（一句话）

三 skill（penpot-sync / penpot-implement / penpot-review）按**人类设计团队职能**切分，但对 LLM 而言它们是同一座"Penpot↔代码桥"的三个阶段。切分制造协调税（R-004/R-005），并掩盖了更深的契约不自洽（R-001）与能力未复用（R-002）。R-001~R-007 是同一根因的不同切面，故按依赖序统一收敛。

## 1. 目标形态

### 1.1 单一能力 `penpot-bridge`，三操作

| 操作 | 取代 | 输入 | 输出 | 触发方 |
|------|------|------|------|--------|
| `read` | penpot-sync 读取腿 | Penpot 组件/Token（MCP） | 结构/真实 CSS/Token 实值/导出图像 | 任意需视觉数据的 agent |
| `generate` | penpot-implement | 语义←ui-spec；样式/几何←Penpot | 组件代码骨架 + 样式（引 tokens.css） | implementer |
| `verify` | penpot-review | 代码 ↔ Penpot（像素权威源） | `docs/reviews/design/DESIGN-REVIEW-*.md` | **reviewer 独占** |

MCP 可用性探测 / 工具发现 / blocked 降级在能力层**统一声明一次**，不再三复制。

### 1.2 权威划分（贯穿全提案的不变量）

| ui-spec 段 | 内容 | 权威源（design_tool=penpot 时） |
|-----------|------|------------------------------|
| §0 设计方向 | 调性/场景/策略 | **ui-spec** |
| §1 设计系统 | Token **命名 + 设计意图** | **ui-spec** |
| §1 设计系统 | Token **实值**（色值/字号/间距数字） | **随 authoring surface**（doc-first 默认 ui-spec / Penpot-first Penpot，存派生快照） |
| §2 组件清单 | UC-NNN 身份 / Props / 状态枚举 / AC 绑定 | **ui-spec** |
| §2 组件清单 | 组件视觉值（精确尺寸/真实 CSS/层级几何） | **随 authoring surface**（同上） |
| §3 页面布局 | 语义结构 / 状态流 / 路由 | **ui-spec** |
| §3 页面布局 | 精确几何 / flex-grid 实参 | **随 authoring surface**（同上） |

绑定键：`UC-NNN ↔ Penpot 组件名/id`。视觉实值同一时刻仅一个权威源：**doc-first**（默认，LLM 在 ui-spec 成形）ui-spec 权威、Penpot 为下游镜像；**Penpot-first**（opt-in，PR-E）Penpot 权威、ui-spec 存派生快照。design_tool=none 时全段回退 ui-spec（纯文本流，缺省）。

### 1.3 三条护栏（任何 PR 不得破坏）

1. **文本契约可审计**：ui-spec.md 仍是 reviewer / code-review 可审的 SSOT；Penpot 提供保真度，不取代契约。
2. **平台可降级**：`design_tool` 默认 `none`；cursor/codex/opencode 可能无 MCP。Penpot 是增强层非硬依赖，无 MCP 时回退纯文本流。
3. **生成≠评判**：`verify` 仅 reviewer 可触发，不让生成者给自己打分。

---

## 2. PR 分解（依赖序 + 优先级）

### PR-A · 权威划分契约化【P0 · 基座 · 无依赖】 — 解 R-001、R-002（契约面）

纯文档/契约改动，无代码，解锁其余全部。

**改动**
- `context/templates/standard/ui-spec.md`（+ `lite/ui-spec-lite.md`、`volumes/ui-spec-theme.md`/`-components.md`/`-pages.md`）：在 §1/§2/§3 的像素段加权威源标注（按 §1.2 表），语义段标注"恒 ui-spec 权威"。
- `penpot-sync/SKILL.md`、`penpot-implement/SKILL.md`、`penpot-review/SKILL.md` 的 能力边界 / Anti-Patterns：把"ui-spec 是唯一/全 source of truth"的笼统措辞，改为"语义→ui-spec，像素→Penpot"。
- penpot-implement：解掉"读 Penpot CSS 但 ui-spec 全权威"自相矛盾——明确样式/几何以 Penpot 为权威、Props/状态以 ui-spec 为权威。
- penpot-review：明确校验方向为 `code → Penpot(像素权威)` 单向，消除"对照源自 ui-spec 的 Penpot"循环表述。

**验收**
- grep 三 skill：不再有"ui-spec 是唯一/全 source of truth"类措辞。
- ui-spec 模板每个像素段有权威源标注。
- `cataforge skill run framework-review -- skills` Layer 1 全绿（B1 必填段未破坏）。

---

### PR-B · 三 skill 收敛为 penpot-bridge【P1 · 依赖 PR-A】 — 解 R-004、R-005

**改动**
- 新建 `.cataforge/skills/penpot-bridge/SKILL.md`：description 含三操作触发词；`argument-hint: "<op: read|generate|verify> <target: UC-NNN|路径>"`；统一 MCP 接线段；≥3 条 Anti-Patterns（B8 底线）；`verify` 段声明"仅 reviewer 触发"。
- 删除 `penpot-sync/`、`penpot-implement/`、`penpot-review/` 三目录（按 §硬约束 1 删到不能再删，不留 alias）。
- `framework.json#/features`：`penpot-sync` → `penpot-bridge`（phase_guard `ui_design` 为最早接入点，描述注明跨 ui_design/development；auto_enable false 不变）。
- 三 AGENT.md `skills:`：ui-designer `penpot-sync`→`penpot-bridge`；implementer `penpot-implement`→`penpot-bridge`；reviewer `penpot-review`→`penpot-bridge`。
- `ui-design/SKILL.md`：Step 3 `penpot-sync`→`penpot-bridge read/token`；Step 9 `penpot-implement`/`penpot-review`→`penpot-bridge generate/verify`。
- `ORCHESTRATOR-PROTOCOLS.md:468`：删"penpot-implement depends penpot-sync"前置依赖表述（合并后无跨 skill 依赖）。
- `docs/reference/agents-and-skills.md`：penpot 三条目合并为一。

**验收**
- `framework-review -- all --focus B2` 交叉引用图无悬空引用、无孤立 skill。
- `.cataforge/` 下 grep `penpot-sync|penpot-implement|penpot-review` 0 命中（CHANGELOG 除外）。
- penpot-bridge 通过 B1（必填段）、B8（Anti-Pattern 底线）。

---

### PR-D · 接入 export_shape 视觉 grounding【P2 · 依赖 PR-B · 可与 PR-C1 并行】 — 解 R-007

低成本高收益（MCP 工具已存在，纯 skill 层）。

**改动**
- `penpot-bridge/SKILL.md`：`read`/`verify` 操作接入 `export_shape`→图像；`verify` 在逐属性比对外增"渲染像素自检"。
- `ui-designer/AGENT.md`：声明设计决策可经 penpot-bridge `read` 取导出图像做视觉自检。

**验收**
- penpot-bridge `read`/`verify` 文档含 export_shape 用途。
- 不破坏既有 DESIGN-REVIEW 报告契约（路径/doc_type 不变）。

---

### PR-C1 · Token reconcile 归一【P2 · 依赖 PR-B · 可与 PR-D 并行】 — 解 R-003、R-006（skill 层）

**改动**
- `penpot-bridge/SKILL.md` token 操作：移除自造"ui-spec/Penpot/tokens.css 三方优先级"reconcile 逻辑；改为 ui-spec §1 经 `cataforge context finalize`/`ingest` 产 tokens.css。
- 去掉无消费者的"单向推 Penpot"主路径；保留为可选"人审镜像导出"（非同步主路径）。
- 移除"禁止双向回写"钝规则，替换为引用 context finalize/ingest 的冲突消解语义。

**验收**
- penpot-bridge token 段不再出现三方手搓优先级表。
- 推 Penpot 降为可选项，缺省路径 ui-spec→tokens.css 经 context 命令。

---

### PR-C2 · Penpot 作为 context 视觉保真 backend【P3 · 依赖 PR-C1 · 可选 · 最大工程】 — 解 R-006（彻底）

把 §1.2 的"像素←Penpot"提升为 context backend 一等公民。

**改动**
- `src/cataforge/`：`cataforge.context` 增 penpot backend 路由（read 像素段 / ingest 回流），经 `framework.json#context.mode` 选择，不可达时降级文件 backend。
- `framework.json#/context`：mode 增 penpot 保真档位声明。

**验收**
- `cataforge context read UC-NNN#visual` 在 design_tool=penpot 时返回 Penpot 像素值、不可达时降级。
- 新增单测覆盖 backend 路由 + 降级。

---

### PR-E · Penpot-first authoring + 视觉回灌【P3 · 依赖 PR-A、PR-C1 · 可选 · 战略 · 可再拆】 — 解 R-002（战略面）

opt-in 项目支持"先在 Penpot 成形 → 反推 ui-spec/代码"的 Figma 式流向。

**改动**
- `penpot-bridge/SKILL.md`：增 `author` 子能力（人或 LLM 经 `execute_code` 在 Penpot 成形组件，经 `generateMarkup`/`generateStyle` 读回）。
- `ui-designer/AGENT.md`：增 Penpot-first authoring 路径——成形后 `cataforge context ingest` 把视觉值回灌 ui-spec §1 实值/§2 视觉/§3 几何段，使 ui-spec 视觉值"派生自"而非"独立臆造"设计。
- 保留无 MCP 降级到纯文本流为缺省。

**验收**
- opt-in 项目可走 Penpot-first，ui-spec 视觉段标记为 Penpot-derived。
- design_tool=none 时该路径不激活，纯文本流不变。

---

## 3. 依赖图与执行顺序

```
PR-A (P0 契约基座)
  └─> PR-B (P1 收敛 penpot-bridge)
        ├─> PR-D  (P2 视觉 grounding)   ┐ 可并行
        └─> PR-C1 (P2 token reconcile)  ┘
                └─> PR-C2 (P3 可选, context backend)
PR-A ─┐
PR-C1 ─┴─> PR-E (P3 可选, Penpot-first 回灌)
```

推进次序：**PR-A → PR-B → (PR-D ∥ PR-C1) → PR-C2 → PR-E**。
P0/P1/P2（A/B/D/C1）为核心收敛，落地后即消除 R-001/R-003/R-004/R-005/R-007 与 R-002 契约面、R-006 主要面。P3（C2/E）为战略增强，可延后或分批。

## 4. 不做（边界）

- 不移除 Penpot 作为 opt-in 的可选性；不把 design_tool 默认改为 penpot。
- 不取消文本契约——ui-spec.md 永远是 reviewer 可审 SSOT。
- 不把 verify 交给非 reviewer 角色。
- 不在本提案引入新的设计工具（Figma/Sketch）；penpot-bridge 抽象保留未来多后端余地，但本提案只实现 Penpot。

## 5. 风险与回滚

- **删三 skill 的迁移面**（PR-B）：下游已部署项目的 agent `skills:` 引用旧名 → 由 `cataforge deploy` 刷新；升级路径在 features 全量覆盖中处理。回滚=恢复三目录 + features 旧条目。
- **context backend 扩展**（PR-C2）：工程量与回归面最大，故置 P3 可选；不做时 PR-C1 的 skill 层归一已消除 R-003 主要危害。
- **Penpot MCP 脆弱性**（已知"握手 Up ≠ 插件已连"）：所有操作保留 blocked 降级；护栏 2 确保无 MCP 时回退纯文本流，不阻断主流程。
