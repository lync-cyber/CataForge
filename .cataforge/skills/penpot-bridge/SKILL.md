---
name: penpot-bridge
description: "Penpot 设计↔代码桥 — read(读结构/样式/Token 实值) · sync(Token 双向同步) · generate(从设计生成组件骨架) · verify(设计↔代码一致性校验)。当 design_tool=penpot 且需在 Penpot 设计与前端代码间读取视觉数据、同步设计 Token、生成组件骨架或校验还原度时使用。read/sync 由 ui-designer 调用，generate 由 implementer 调用，verify 由 reviewer 独占。"
argument-hint: "<op: read|sync|generate|verify> <target: UC-NNN|代码路径|sync-direction>"
suggested-tools: file_read, file_write, file_edit, file_glob, file_grep
depends: [context]
disable-model-invocation: false
user-invocable: true
---

# Penpot 设计↔代码桥 (penpot-bridge)

## 能力边界
- 能做: 读 Penpot 组件结构/样式/Token 实值；Token 双向同步（ui-spec ↔ Penpot ↔ tokens.css）；从 Penpot 设计生成组件代码骨架；设计↔代码视觉一致性校验
- 不做: 需求/架构/页面信息设计（由 ui-design 负责）；业务逻辑/状态管理/API 对接（由 TDD GREEN 负责）；修改 ui-spec 语义契约

> 权威划分（语义 vs 视觉实值）见 ui-spec 模板「权威源约定」。

## 前置条件（所有操作共用）
- {INSTRUCTION_FILE} `设计工具` 字段为 `penpot`
- Penpot MCP 可用（见 §Penpot MCP 接入）；不可用时返回 blocked，不静默 success

## 输入规范
- read: UC-{NNN} 或 Penpot 组件名
- sync: ui-spec#§1 设计系统 Token + sync-direction ∈ {emit, mirror, ingest}
- generate: ui-spec#§2 UC-{NNN}（Props/变体/交互——语义）+ arch#§1.4 技术栈 + Penpot 组件设计数据（视觉，经 read）
- verify: Penpot 组件设计数据（视觉权威源，经 read）+ 已实现组件代码路径 + ui-spec#§2 UC-{NNN}（语义参照）

## 输出规范
- read: 组件层级结构 / CSS 属性 / Token 实值 + 组件导出图像（供其他操作复用）
- sync: `src/styles/tokens.css`（W3C Design Tokens 格式）+ 同步差异报告
- generate: 组件骨架文件（按 arch 技术栈）+ 样式文件（引 tokens.css 变量）
- verify: 设计一致性审查报告 `docs/reviews/design/DESIGN-REVIEW-{component_id}-r{N}.md`（差异列表 + 修复建议）

## Penpot MCP 接入
具体 MCP 工具名以平台 MCP 配置为准（Claude: `.mcp.json` / `.claude/settings.json`；Cursor: `.cursor/mcp.json`；OpenCode: `opencode.json`），运行时按可用工具列表自动发现。典型操作：读项目信息、读组件结构/样式/SVG、读写设计 Token、导出组件图像（export_shape）。工具列表中无 Penpot 工具时先 `cataforge penpot ensure`（若未部署则 `cataforge penpot deploy`），仍不可用返回 blocked。

## 操作指令

### read
读 Penpot 设计数据，供 sync/generate/verify 复用或独立做视觉 grounding。
1. 经 MCP 读取组件层级结构（容器/子元素/文本/图标）
2. 提取 CSS 属性（尺寸/颜色/字体/间距/边框）与 Token 实值
3. 映射到 tokens.css 设计变量（优先变量而非硬编码值）
4. 经 MCP `export_shape` 导出目标组件图像，供调用方做视觉自检（设计决策 / 还原度核对）

### sync
ui-spec §1 Token 与 Penpot / tokens.css 对齐。tokens.css 是 ui-spec §1 的单向派生（非独立权威源）；ui-spec 自身的 graph 回流由 `cataforge context ingest` 负责，本操作只跨 ui-spec ↔ Penpot 一条边。按 sync-direction：
1. emit（doc-first 缺省）：从 ui-spec §1 Token 表确定性生成 `src/styles/tokens.css`（单向投影，不读回 tokens.css 改 ui-spec）+ 差异报告
2. mirror（可选）：把 ui-spec §1 Token 单向推 Penpot 作镜像；无自动化消费者，可跳过
3. ingest（Penpot-first）：read Penpot Token 实值 → 写入 ui-spec §1 md → 由 orchestrator 在收口点跑 `cataforge context ingest` 回流图后端；仅同步差异项，不全量覆盖

### generate
从 Penpot 设计生成组件代码骨架。
1. read 目标组件设计数据，加载 ui-spec UC-{NNN} 与 arch#§1.4 技术栈
2. 按技术栈生成组件结构（基于 Penpot 层级）、Props 接口（基于 ui-spec UC-{NNN}）、变体（default/hover/active/disabled/error）、样式（引 tokens.css 变量）、交互钩子（基于 ui-spec 交互描述）
3. 只产骨架/样式/静态资源；业务逻辑由 TDD GREEN 补充

### verify（reviewer 独占）
比对 Penpot 设计与代码实现的视觉一致性。
1. read 目标组件视觉属性（颜色/排版/间距/尺寸/布局——视觉权威源）
2. 从组件代码提取实际样式值，识别 tokens.css 变量引用
3. 逐属性比对：完全匹配 / Token 间接匹配 → PASS；值不匹配 → DIFF（记设计值 vs 代码值 vs 偏差）；设计有代码缺 → MISSING；代码有设计无 → EXTRA（仅记录）；<1px 偏差标 WARN 非 DIFF
4. 经 `export_shape` 导出设计图像与已实现组件渲染对照，捕获逐属性比对漏掉的整体视觉偏差（布局错位 / 视觉层次失真），归入 DIFF / WARN；仅静态视觉，忽略交互/动画
5. 产出 DESIGN-REVIEW 报告（front matter 见 COMMON-RULES §报告 Front Matter 约定）

## Anti-Patterns
- 禁止: 用 Penpot 覆盖 ui-spec 的语义契约 —— 组件身份/Props/状态枚举/AC 绑定恒以 ui-spec 为权威源，仅视觉实值随 authoring surface；否则语义漂移绕过 reviewer 校对
- 禁止: 在 Penpot 未启动时静默返回 success —— `cataforge penpot ensure` 失败必须返回 blocked，否则 generate 在空数据上施工、sync 写空 Token
- 禁止: generate 越界产业务逻辑 —— 只产骨架/样式/静态资源；业务逻辑由 TDD GREEN 补充，越界会让 RED 测试无法约束实现
- 禁止: verify 由非 reviewer 触发或自动回写 ui-spec —— verify 只产差异报告供 reviewer 把关；生成者给自己打分会失去审查独立性
- 禁止: sync 把 tokens.css 当独立权威源参与 reconcile —— tokens.css 是 ui-spec §1 的单向派生；反向读 tokens.css 改 ui-spec 会制造伪三方 reconcile
- 禁止: sync 全量覆盖远端 Token —— 局部增量同步保留 Penpot 端手动微调，全量覆盖丢失未提交回 ui-spec 的中间状态
- 避免: 组件样式硬编码而不引 tokens.css 变量 —— 全局风格调整需全文件搜索替换

## 效率策略
- read 结果在 sync/generate/verify 间复用，不重复经 MCP 拉取
- 优先 tokens.css 变量而非硬编码值，保证全局一致
- verify 仅比对静态视觉属性，忽略交互/动画；Token 间接匹配视为通过
