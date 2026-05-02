---
name: doc-gen
description: "统一文档生成 — 模板实例化、内容填充、文档拆分、索引注册。"
argument-hint: "<操作: create|write-section|finalize> <template_id> <project> <version>"
suggested-tools: Read, Write, Edit, Glob
depends: []
disable-model-invocation: false
user-invocable: true
---

# 统一文档生成 (doc-gen)
## 能力边界
- 能做: 模板实例化、章节内容填充、超长文档拆分、机器索引注册、交叉引用生成
- 不做: 内容决策(由调用Agent负责)、文档评审(由doc-review负责)、机器索引重建（由 `cataforge docs index` 负责，doc-gen 仅触发增量更新）

## 操作指令

### 指令1: 创建文档骨架 (create)
当Agent需要创建新文档时，按以下步骤执行:
1. 查阅注册表: `Read .cataforge/skills/doc-gen/templates/_registry.yaml`，找到 `{template_id}` 条目的 `path` 字段
   读取模板文件: `Read .cataforge/skills/doc-gen/templates/{path}`（如 `standard/prd.md`）
2. 替换占位符: `{项目名称}` → 项目名, `{project}` → 项目标识(slug, 仅限 `[a-z0-9-]`), `{ver}` → 版本号(写入 frontmatter `version:` 字段)
3. 设置文档头:
   - `id` 格式 `{template_id}-{project}` —— **不带版本号**。id 是稳定身份，跨版本不变；版本归 `version:` 字段
   - `version: "{ver}"`（独立字段；可含 `.`，但不进入 id/文件名）
   - author(当前agent目录名)、status=draft、deps(按模板)、consumers(按模板)
4. 写入文件（Write 工具会自动创建不存在的父目录）: `Write docs/{doc_type}/{template_id}-{project}.md`
   - doc_type 映射见下方 template_id 映射表
   - 特殊映射: research-note → `docs/research/`, changelog → `docs/changelog/`, brief → `docs/brief/`
5. 返回给Agent: 目标文件路径 + 必填章节清单(从[NAV]块提取)

> **命名规则（强制）**: `id` 与文件名只允许 `[a-z0-9-]`（slug）。**禁止**把版本号、点号、空格塞进 id —— `cataforge docs validate` 会 FAIL，并阻塞 doctor / CI。版本演进时 id/文件名保持稳定，仅更新 `version:` 字段；同一项目不同版本会**覆盖**同一份 doc（要保留历史走 git 或归档目录）。

### 指令2: 写入章节内容 (write-section)
Agent逐章填充内容时:
1. 读取目标文档: 通过 `docs/.doc-index.json` 定位准确路径（或直接拼接 `docs/{doc_type}/{filename}` 后 Read）
2. 定位章节标题(如 `## 2. 功能需求`)
3. 使用 `Edit` 工具写入章节内容
4. 如果内容引用了其他文档(如 F-001 → arch#M-001)，检查引用目标是否存在

### 指令3: 完成文档 (finalize)
文档所有章节填充完毕后:
1. 结构完整性检查(非内容验证): 确认所有必填章节存在且非空、文档头字段齐全(id/author/status/deps/consumers)。仅检查结构，不评估内容质量；内容验证由 doc-review 负责。
   - **检查通过**: 继续 Step 2
   - **检查失败**: 返回缺失项清单给调用 Agent，不执行 Step 2-4。Agent 应补充缺失章节后重新调用 finalize
2. 拆分判断: 如文档行数超过 `DOC_SPLIT_THRESHOLD_LINES`，按下方"文档拆分策略"执行拆分
3. 更新机器索引: `cataforge docs index --doc-file {最终文档路径}` —— 增量刷新 `docs/.doc-index.json`，doc-nav 后续按 doc_id 即可定位
4. **[EVENT]** `cataforge event log --event doc_finalize --phase {当前阶段} --ref "{doc_id}" --detail "文档finalize: {doc_id}"`
5. 返回: 最终文档路径 + .doc-index.json 更新确认

注: doc-gen 不再写入 markdown 形式的 NAV-INDEX；唯一持久化的索引是机器可读的 `docs/.doc-index.json`，由 `cataforge docs index` 维护。

注意: finalize 是轻量格式预检；深度内容审查由 doc-review 负责

## 文档拆分策略
触发条件: 单文档行数超过 `DOC_SPLIT_THRESHOLD_LINES`

### 拆分映射表
> 命名规则只用 slug（`[a-z0-9-]`），版本号一律下沉到 frontmatter `version:` 字段。

| doc_type | volume_type | 保留章节 | 命名规则 | 模板文件 |
|----------|-------------|----------|----------|----------|
| prd | main | §1概述, §3非功能需求, §4约束, §5术语 | `prd-{project}.md` | `templates/prd.md` |
| prd | features | §2功能需求 (F-{start}..F-{end}) | `prd-{project}-f{start}-f{end}.md` | `templates/prd-volume.md` |
| arch | main | §1架构概览, §5非功能架构, §6目录, §7约定 | `arch-{project}.md` | `templates/arch.md` |
| arch | modules | §2模块划分 (M-001..M-NNN) | `arch-{project}-modules.md` | `templates/arch-modules.md` |
| arch | api | §3接口契约 (API-001..API-NNN) | `arch-{project}-api.md` | `templates/arch-api.md` |
| arch | data | §4数据模型 (E-001..E-NNN) | `arch-{project}-data.md` | `templates/arch-data.md` |
| dev-plan | main | §1迭代规划, §2依赖图, §4关键路径, §5风险 | `dev-plan-{project}.md` | `templates/dev-plan.md` |
| dev-plan | sprint | §3任务卡详细 — 单Sprint | `dev-plan-{project}-s{N}.md` | `templates/dev-plan-sprint.md` |
| ui-spec | main | §1设计系统, §4导航路由, §5响应式 | `ui-spec-{project}.md` | `templates/ui-spec.md` |
| ui-spec | components | §2组件清单 (C-{start}..C-{end}) | `ui-spec-{project}-c{start}-c{end}.md` | `templates/ui-spec-components.md` |
| ui-spec | pages | §3页面布局 (P-{start}..P-{end}) | `ui-spec-{project}-p{start}-p{end}.md` | `templates/ui-spec-pages.md` |

### 拆分执行步骤
1. **确定拆分方案** — 根据上表确定 doc_type 对应的 volume_type 组合
2. **创建分卷骨架** — 使用分卷模板 (`templates/{模板文件}`) 创建各分卷文件
3. **移动内容** — 将主卷中对应章节内容移入分卷，主卷保留交叉引用目录
4. **更新机器索引** — 拆分完成后对每个分卷分别运行 `cataforge docs index --doc-file <分卷路径>`；`split_from` 字段写入分卷的 YAML Front Matter，indexer 会自动读取
5. **分卷存放路径** — 与主卷同目录: `docs/{doc_type}/`

### 拆分规则
- 主卷保留全局概览和交叉引用目录
- 每个分卷 YAML Front Matter 包含 `volume_type: {type}` 和 `split_from: "{主卷ID}"`
- 分卷间通过ID引用
- 拆分不改变ID编号体系

## 持有模板
模板位于 `.cataforge/skills/doc-gen/templates/`，完整映射见下方 §template_id 映射表。

### template_id 映射表
| template_id | 模板文件 | doc_type | 作者Agent | 上游依赖 |
|-------------|----------|----------|-----------|----------|
| prd | templates/prd.md | prd | product-manager | none |
| arch | templates/arch.md | arch | architect | prd |
| ui-spec | templates/ui-spec.md | ui-spec | ui-designer | prd, arch |
| dev-plan | templates/dev-plan.md | dev-plan | tech-lead | arch, ui-spec |
| test-report | templates/test-report.md | test-report | qa-engineer | dev-plan |
| deploy-spec | templates/deploy-spec.md | deploy-spec | devops | arch |
| research-note | templates/research-note.md | research | any | — |
| changelog | templates/changelog.md | changelog | devops | — |
| prd-volume | templates/prd-volume.md | prd | product-manager | prd |
| arch-modules | templates/arch-modules.md | arch | architect | prd |
| arch-api | templates/arch-api.md | arch | architect | prd |
| arch-data | templates/arch-data.md | arch | architect | prd |
| dev-plan-sprint | templates/dev-plan-sprint.md | dev-plan | tech-lead | arch, ui-spec |
| ui-spec-components | templates/ui-spec-components.md | ui-spec | ui-designer | prd, arch |
| ui-spec-pages | templates/ui-spec-pages.md | ui-spec | ui-designer | prd, arch |
| brief | templates/brief.md | brief | product-manager | none |
| prd-lite | templates/prd-lite.md | prd | product-manager | none |
| arch-lite | templates/arch-lite.md | arch | architect | prd-lite |
| ui-spec-lite | templates/ui-spec-lite.md | ui-spec | ui-designer | prd-lite |
| dev-plan-lite | templates/dev-plan-lite.md | dev-plan | tech-lead | arch-lite |

> **执行模式说明**: `brief` 仅用于 agile-prototype 模式（合并 PRD+ARCH+DEV-PLAN）；`prd-lite` / `arch-lite` / `dev-plan-lite` 仅用于 agile-lite 模式；`ui-spec-lite` 为 agile-lite 模式的可选项，仅当项目涉及 UI 时生成。模式判定见 COMMON-RULES §执行模式矩阵。lite 文档与 standard 文档共享同一 `docs/{doc_type}/` 目录（如 `docs/prd/prd-lite-{project}.md`），同一项目只会选用其中一种。

## 通用文档头规范
每份文档必须以 YAML Front Matter 开始:
```yaml
---
id: "{type}-{project}"          # slug only: [a-z0-9-]; 不含版本号
version: "{ver}"                 # 版本号在这里，可含 '.'，但绝不进入 id/文件名
doc_type: {type}
author: {agent-name}
status: draft
deps: [{上游文档ID列表}]         # 同样使用稳定 id，跨版本不变
consumers: [{下游agent列表}]
volume: main
# 仅分卷文档需要以下字段:
# volume_type: {features|modules|api|data|sprint|components|pages}
# split_from: "{主卷ID}"          # 不含 {ver}
required_sections:
  - "## 1. {章节名}"
---
# {文档类型}: {项目名称}

[NAV]
- §1 {章节名} → {子章节列表}
...
[/NAV]
```

## 效率策略
- 按模板生成骨架，减少Agent的格式化工作
- finalize 时自动调用 `cataforge docs index` 增量更新 `.doc-index.json`，避免手动维护
- 拆分后每个分卷可独立加载，支持按需消费
