# Task 1 — 现有文档系统审计

> KG Migration 0.5.0 · Agent-T1 产出 · 基于 codebase 0.4.1 实际代码读取

---

## §1.1 Markdown 文档生成流

### 触发方

| 触发者 | 触发方式 | 说明 |
|--------|---------|------|
| Agent（产品经理/架构师/UI设计师/Tech-Lead/QA/DevOps） | 调用 `doc-gen` skill 的 `create` / `write-section` / `finalize` 指令 | 每个 SDLC 角色 Agent 在对应阶段主动调用 |
| Orchestrator | 通过 `agent-dispatch` 激活对应角色 Agent，角色 Agent 再调用 doc-gen | Bootstrap 阶段初始化文档骨架 |
| 手动 / CLI | `cataforge docs index` / `cataforge docs validate` | 维护索引，不生成文档内容 |
| PostToolUse Hook（`lint_format`） | 文件写入后自动格式化 | 不生成文档，但对生成后的文件做 in-place 修改 |

### 生成时机

| 时机 | 操作 |
|------|------|
| Phase 启动（`create` 指令） | 基于模板实例化文档骨架，写入 YAML Front Matter + NAV 块 + 章节占位符 |
| 章节填充中（`write-section` 指令） | Agent 逐章用 `Edit` 工具写入内容 |
| 章节全部完成后（`finalize` 指令） | 结构完整性检查 → 触发 `cataforge docs index --doc-file` 增量更新索引 → 发射 `doc_finalize` 事件 |
| 文档行数超 `DOC_SPLIT_THRESHOLD_LINES`（300行） | doc-gen 执行拆分，创建分卷文件，分别触发增量索引更新 |

### 写入路径与命名规则

```
docs/{doc_type}/{template_id}-{project}.md
```

- `doc_type`：`prd` / `arch` / `ui-spec` / `dev-plan` / `test-report` / `deploy-spec` / `research` / `changelog` / `brief`
- `template_id`：与 `doc_type` 同名（主卷）
- 分卷命名：`{template_id}-{project}-{suffix}.md`（后缀见下表）

| 分卷类型 | 命名后缀示例 |
|---------|------------|
| prd features | `prd-{project}-f{start}-f{end}.md` |
| arch modules | `arch-{project}-modules.md` |
| arch api | `arch-{project}-api.md` |
| arch data | `arch-{project}-data.md` |
| dev-plan sprint | `dev-plan-{project}-s{N}.md` |
| ui-spec components | `ui-spec-{project}-c{start}-c{end}.md` |
| ui-spec pages | `ui-spec-{project}-p{start}-p{end}.md` |

审查报告写入 `docs/reviews/{doc,code,sprint,retro}/` 目录，命名 `REVIEW-{doc_id}-r{N}.md`。

### 业务文档 vs 框架资产区分

| 类别 | 路径 | 分类 |
|------|------|------|
| 用户软件项目产物 | `docs/prd/*.md`, `docs/arch/*.md`, `docs/ui-spec/*.md`, `docs/dev-plan/*.md`, `docs/test-report/*.md`, `docs/deploy-spec/*.md`, `docs/research/*.md`, `docs/changelog/*.md`, `docs/brief/*.md`, `docs/reviews/**/*.md` | **业务文档** |
| 框架元文件 | `.cataforge/skills/*/SKILL.md`, `.cataforge/agents/*/AGENT.md`, `.cataforge/rules/*.md`, `.cataforge/hooks/hooks.yaml`, `.cataforge/schemas/*.json` | **框架资产** |
| 机器索引 | `docs/.doc-index.json` | 介于两者之间，索引的是业务文档，由框架维护 |

---

## §1.2 加载与查询流

### 主路径：`cataforge docs load` CLI

**函数签名**（`src/cataforge/domain/docs/loader.py`）：

```python
def extract(ref: str, project_root: str, file_cache: dict[str, list[str]] | None = None) -> str
# ref 格式: "doc_id#§N"  /  "doc_id#§N.M"  /  "doc_id#§N.ITEM-xxx"
# 返回: 目标章节的 Markdown 文本（字符串）

def extract_batch(refs: list[str], project_root: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]
# 返回: (successes=[(ref, content)], errors=[(ref, message)])

def plan_load(refs: list[str], project_root: str, token_budget: int) -> tuple[list[str], list[str]]
# 返回: (loadable_refs, deferred_refs)

def resolve_deps(ref: str, project_root: str, max_depth: int = 2) -> list[str]
# 返回: 依赖 ref 列表（从 .doc-index.json 的 deps 字段读取，DFS 深度≤2）
```

**查询两阶段**：
1. 优先走 O(1) 索引查表（`docs/.doc-index.json`），命中则直接按 `line_start/line_end` 切片
2. 索引缺失或过期（文件 mtime > index `generated_at`）时回退到 Markdown 标题扫描（`iter_markdown_headings`）

### 降级路径（Bash 不可用时）

Agent 直接读取 `docs/.doc-index.json`，按 `file_path` + `line_start` + `line_end` 字段调用 `Read` 工具精确读取。

### 查询结果消费方式

| Agent | 消费方式 |
|-------|---------|
| 所有 SDLC 角色 Agent | 通过 Bash `cataforge docs load <ref>` 获取文本 → 直接注入当前 LLM 上下文，作为写文档/决策的输入 |
| doc-review Layer 2 | 通过 `doc-nav` 按需加载被审文档及上游依赖 → 注入 AI 审查 |
| sprint-review Layer 2 | 通过 `doc-nav` 加载 dev-plan + arch + CODE-REVIEW 报告 → 注入 AI 审查 |
| task-dep-analysis | 读取 dev-plan 文档提取 T-xxx 依赖边 → 输入图算法脚本 |
| `cataforge docs validate` | 通过 `indexer.validate_docs()` 批量读取索引和磁盘文件做完整性校验 |

---

## §1.3 工具调用点清单

| Call site | Tool function | Query type | Frequency | Return shape | Access object class |
|-----------|--------------|------------|-----------|--------------|---------------------|
| architect/AGENT.md `Input Contract` | `cataforge docs load prd#§1 prd#§3 prd#§2.F-xxx` | exact（指定 doc_id + section + item） | 每次 architect 启动 | Markdown 文本，stdout `=== ref ===\n<content>` | Business doc |
| tech-lead/AGENT.md `Input Contract` | `cataforge docs load arch#§2.M-xxx arch#§3.API-xxx ui-spec#§2.C-xxx ui-spec#§3.P-xxx` | exact（item 级） | 每次 tech-lead 启动 | Markdown 文本 | Business doc |
| qa-engineer/AGENT.md `Input Contract` | `cataforge docs load dev-plan#§2.T-xxx arch#§3.API-xxx` | exact（item 级） | 每次 QA 启动 | Markdown 文本 | Business doc |
| devops/AGENT.md `Input Contract` | `cataforge docs load arch#§1.4 arch#§6 arch#§7` | exact（section 级） | 每次 devops 启动 | Markdown 文本 | Business doc |
| ui-designer/AGENT.md `Input Contract` | `cataforge docs load prd#§2.F-xxx arch#§2.M-xxx arch#§3.API-xxx` | exact（item 级） | 每次 ui-designer 启动 | Markdown 文本 | Business doc |
| doc-review Layer 2 (doc-review/SKILL.md) | `cataforge docs load <被审文档 + 上游依赖章节>` via doc-nav | exact + dependency chain（`--with-deps`） | 每次 doc-review Layer 2 | Markdown 文本 | Business doc |
| sprint-review Layer 2 (sprint-review/SKILL.md) | `cataforge docs load dev-plan#§N.T-xxx arch#§3.API-xxx` via doc-nav | exact（batch） | 每次 sprint-review Layer 2 | Markdown 文本 | Business doc |
| task-dep-analysis/SKILL.md Step 1 | Read + Grep 直接读 dev-plan 文档 | scan（全文提取 T-xxx 依赖行） | tech-lead 生成 dev-plan 后 | 文本行（边列表） | Business doc |
| doc-gen finalize Step 3 | `cataforge docs index --doc-file <path>` → `indexer.update_single_doc()` | write（增量写索引） | 每次文档 finalize | 更新 `.doc-index.json` | Business doc |
| orchestrator Bootstrap Step 9 | `cataforge docs index`（无 `--doc-file`，全量） | write（全量重建） | 项目初始化一次 | 写 `.doc-index.json` | Business doc |
| `cataforge docs validate` (docs_cmd.py) | `indexer.validate_docs()` | scan（全索引校验） | CI / pre-commit / 手动 | dict: `{orphans, stale, xref_errors, alias_conflicts, invalid_ids, stale_deps}` | Business doc |
| doc-review Layer 1 `check_xref()` (checker.py) | `re.findall(r"([\w-]+)#([\w§.\-]+)", content)` + `Path(docs_dir).glob(f"{doc_id}*")` | regex scan + filesystem glob | 每次 Layer 1 检查 | FAIL/PASS 列表 | Business doc |
| doc-review Layer 1 `check_bidirectional_coverage()` | `docs_path.glob(f"**/{upstream_type}*.md")` + `re.finditer(rf"^### ({upstream_prefix}-\d+)")` | filesystem scan + regex | 每次 Layer 1 检查（主卷） | FAIL/PASS 列表 | Business doc |
| `loader._load_doc_type_map()` | 读取 `.cataforge/framework.json` `docs.doc_types` | exact（key lookup） | 每个 project_root 首次调用 | `dict[str, str]` doc_id→subdirectory | Mixed（读框架配置，索引业务文档） |
| doc-nav 降级路径 | `Read docs/.doc-index.json` → `Read docs/{doc_type}/{file}` offset/limit | exact（行号范围） | Bash 不可用的 Agent | Markdown 文本行 | Business doc |
| `indexer.build_xref()` | 扫描所有 `doc_entry.sections.items` 提取 ITEM_ID_RE 匹配项 | scan（全量） | 每次 `cataforge docs index` | `dict[item_id, [{doc_id, section, file_path}]]` | Business doc |
| framework-review SKILL（`_framework_data.py`） | 读取 `.cataforge/skills/**/SKILL.md`，`.cataforge/agents/**/AGENT.md` | filesystem scan | 每次 framework-review 运行 | 框架资产结构化数据 | Framework asset |

---

## §1.4 结构性缺陷（有据可查）

### 缺陷驱动1：LLM 查询低效（token 消耗 / 检索精度）

**案例 A：回退扫描全文标题**

`loader.extract()` 在索引缺失或过期时，回退路径是调用 `iter_markdown_headings(content)` 对文件全文做 markdown-it 解析（`src/cataforge/domain/docs/loader.py:384-391`）。`iter_markdown_headings` 内部走完整 CommonMark 解析器（`md_parse.py:8-36`），对一个 300 行的 arch 主卷来说，每次 fallback 都要解析整个文件，且仅为了定位一个 section 的行号范围。索引失效（7 天 stale 告警阈值在 `_STALE_DAYS_WARN = 7`）期间每个 Agent 每次调用均退化为此路径。

**案例 B：doc-review Layer 1 `check_xref()` 正则宽泛**

`checker.py:138-157` 的 xref 检查用 `re.findall(r"([\w-]+)#([\w§.\-]+)", content)` 扫描全文，任何含 `#` 的模式都会命中（包括注释、代码块内的 URL fragment、YAML 值中的锚点）。代码块剥除（`_strip_code_blocks`）用 ` ```.*?``` ` 正则，无法处理嵌套或带语言标注的代码块中的非标准格式。误命中的字符串再走 `Path.glob(f"{doc_id}*")` 文件系统查找，每个误命中都产生一次 IO。

### 缺陷驱动2：文档腐化（编号错误、更新遗漏、内容漂移）

**案例 A：ID 连续性检查是事后告警，非阻塞门禁**

`checker.py:196-214` 的 `check_id_continuity()` 结论是 `self.warn()`（WARN 而非 FAIL）。这意味着 F-001 / F-003 跳号（缺 F-002）在 Layer 1 通过后会进入 Layer 2 AI 审查，但不会阻塞 `doc-gen finalize`。审查报告以 WARN 记录，不进入 `needs_revision` 判定路径（三态判定只在 CRITICAL/HIGH 问题存在时才触发 `needs_revision`，见 `COMMON-RULES §三态判定逻辑`）。

**案例 B：`dep_hashes` 过期不自动触发文档更新**

`indexer.find_stale_deps()` 检测上游文档 `content_hash` 变化（`indexer.py:304-341`），但仅在 `cataforge docs validate` / `cataforge doctor` 时输出 WARN，不会主动触发下游 Agent 重新读取并更新文档。如果 arch 修改了 M-001 的接口定义，dev-plan 中引用该模块的 T-xxx 任务卡 `context_load` 字段不会自动失效或通知——只有人工运行 validate 才能发现 `dep_hashes` 不一致。

### 缺陷驱动3：跨文档语义关系依赖正则匹配

**案例 A：双向覆盖检查的假阳性**

`checker.py:222-270` 的 `check_bidirectional_coverage()` 用 `re.search(re.escape(item), content_no_code)` 判断 arch 是否覆盖 PRD 的 F-NNN。这是字符串存在性判断：只要 arch 文档正文中出现了字符串 `F-001`（哪怕是在注释、废弃段落、或仅作为举例引用），就算"已覆盖"。实际上 M-001 可能只提到"参见 F-001 背景"而未真正实现该功能。此类假阳性会导致覆盖检查 PASS 但实际存在功能遗漏。

**案例 B：xref 检查的假阴性（跨分卷引用）**

`check_xref()` 用 `docs_path.glob(f"{doc_id}*")` 查找文件（`checker.py:149-156`），其中 `docs_path` 是传入的 `docs_dir` 参数（doc_type 子目录）。如果 arch-api 分卷引用了 `prd#§2.F-001`，其 `docs_dir` 为 `docs/arch/`，`docs_path.glob("prd*")` 在 `docs/arch/` 下找不到任何文件，触发 FAIL 误报。代码有三级 fallback（`docs_path` → `docs_path.parent` → `parent.glob("**/{doc_id}*")`），但最后一级是无目录层级限制的递归 glob，可能跨 `docs/reviews/` 等目录误命中非 business doc 文件而产生假阴性（以为找到了但文件内容不匹配）。

---

## §1.5 调用关系图

```mermaid
flowchart TD
    User([用户 / 需求输入]) --> Orchestrator

    Orchestrator -->|agent-dispatch| PM[product-manager]
    Orchestrator -->|agent-dispatch| Arch[architect]
    Orchestrator -->|agent-dispatch| UI[ui-designer]
    Orchestrator -->|agent-dispatch| TL[tech-lead]
    Orchestrator -->|agent-dispatch| QA[qa-engineer]
    Orchestrator -->|agent-dispatch| DevOps[devops]

    PM -->|doc-gen create/write-section/finalize| DocGen[doc-gen skill]
    Arch -->|doc-gen create/write-section/finalize| DocGen
    UI -->|doc-gen create/write-section/finalize| DocGen
    TL -->|doc-gen create/write-section/finalize| DocGen
    QA -->|doc-gen create/write-section/finalize| DocGen
    DevOps -->|doc-gen create/write-section/finalize| DocGen

    DocGen -->|Write| FS[(docs/ 文件系统)]
    DocGen -->|cataforge docs index --doc-file| Indexer

    Arch -->|cataforge docs load prd#§N| Loader
    UI -->|cataforge docs load prd#§N arch#§N| Loader
    TL -->|cataforge docs load arch#§N ui-spec#§N| Loader
    QA -->|cataforge docs load dev-plan#§N| Loader
    DevOps -->|cataforge docs load arch#§N| Loader

    Loader -->|1. O(1) 索引查表| IndexFile[docs/.doc-index.json]
    Loader -->|2. fallback: markdown-it 标题扫描| FS

    Indexer -->|build_full_index / update_single_doc| IndexFile
    Indexer -->|读取 docs/**/*.md| FS

    DocRev[doc-review skill] -->|Layer 1: cataforge skill run doc-review| DocChecker[DocChecker Python]
    DocRev -->|Layer 2: cataforge docs load via doc-nav| Loader
    DocChecker -->|regex scan + glob| FS

    SprintRev[sprint-review skill] -->|Layer 1: cataforge skill run sprint-review| SprintChecker[sprint_check.py]
    SprintRev -->|Layer 2: doc-nav load| Loader

    TL -->|cataforge skill run task-dep-analysis| DepAnalysis[task-dep-analysis script]
    DepAnalysis -->|Read / Grep dev-plan| FS

    CLI[cataforge docs validate] -->|indexer.validate_docs| IndexFile
    CLI -->|find_orphan_docs: glob docs/**/*.md| FS

    Hook[PostToolUse: lint_format] -->|in-place rewrite| FS
    Hook2[PostToolUse: log_agent_dispatch] -->|append| EventLog[docs/EVENT-LOG.jsonl]
```

---

## §1.6 业务文档中的领域实体清单

### doc_type → SDLC 层映射

| doc_type | SDLC 语义层 | 执行模式 |
|----------|------------|---------|
| `prd` | 需求层（What / Why） | standard |
| `prd-lite` | 需求层（轻量） | agile-lite |
| `brief` | 需求+架构+计划合并层（原型） | agile-prototype |
| `arch` | 架构层（How at system level） | standard |
| `arch-lite` | 架构层（轻量） | agile-lite |
| `ui-spec` | 界面规范层（What to display） | standard |
| `ui-spec-lite` | 界面规范层（轻量，可选） | agile-lite |
| `dev-plan` | 开发计划层（task breakdown） | standard |
| `dev-plan-lite` | 开发计划层（轻量） | agile-lite |
| `test-report` | 测试验证层 | standard |
| `deploy-spec` | 部署运维层 | standard |
| `research` | 调研辅助层（支撑决策，非 SDLC 主链） | any |
| `changelog` | 发布记录层 | any |
| `sprint-review`（报告） | Sprint 完成度审计层 | standard / agile-lite |

### frontmatter ID 模式 → 实体类型映射

以下条目从模板文件、checker.py 的 `id_patterns`、SKILL.md 约定中提取：

| ID 模式 | 实体类型 | 所在文档 | 编号约定 |
|---------|---------|---------|---------|
| `F-NNN` | Feature（功能需求） | prd（§2）, prd-lite（§2）, prd-volume（§2） | 3位零填充，从 F-001 连续递增 |
| `AC-NNN` | AcceptanceCriteria（验收标准） | prd（§2.F-xxx 内），dev-plan（T-xxx.tdd_acceptance） | 全局连续或 per-Feature 连续 |
| `M-NNN` | Module（架构模块） | arch（§2）, arch-modules（§2） | 3位零填充，M-001 起 |
| `API-NNN` | APIContract（接口契约） | arch（§3）, arch-api（§3） | 3位零填充，API-001 起 |
| `E-NNN` | Entity（数据实体） | arch（§4）, arch-data（§4） | 3位零填充，E-001 起 |
| `C-NNN` | Component（UI 组件） | ui-spec（§2）, ui-spec-components（§2） | 3位零填充，C-001 起 |
| `P-NNN` | Page（UI 页面） | ui-spec（§3）, ui-spec-pages（§3） | 3位零填充，P-001 起 |
| `T-NNN` | Task（开发任务卡） | dev-plan（§3）, dev-plan-sprint（§3） | 3位零填充，T-001 起 |
| `TC-NNN` | TestCase（测试用例） | test-report（§2 用例矩阵） | [待验证: 模板中用 "用例ID" 列，无统一 TC-NNN 强制格式，实际项目可能用不同前缀] |
| `SR-NNN` | SprintReviewIssue | SPRINT-REVIEW-sN-rM.md | 3位零填充，SR-001 起 |

### 跨文档引用关系（可追溯性矩阵原始信号）

以下引用关系通过模板、AGENT.md 约定、checker.py `check_bidirectional_coverage()` 和 `check_arch()` 实际验证逻辑推断：

| 源文档 | 引用目标文档 | 引用实体 | 引用方向语义 | 验证机制 |
|--------|------------|---------|------------|---------|
| arch | prd | F-NNN | 每个 M-NNN 必须映射 ≥1 个 F-NNN（"映射功能"字段） | `check_bidirectional_coverage()` FAIL |
| arch (API-NNN) | prd | F-NNN | [待验证: API 模板无强制 F-NNN 引用字段] | 无强制检查 |
| ui-spec (C-NNN) | prd | F-NNN | 每个 C-NNN 有"映射功能"字段引用 F-NNN | `check_bidirectional_coverage()`（ui-spec→prd） FAIL |
| ui-spec (P-NNN) | prd | F-NNN | P-NNN 的"映射功能"字段 | 同上 |
| ui-spec (C-NNN) | arch | API-NNN | `context_load` 字段声明 | 无自动验证，doc-nav 按需加载 |
| dev-plan (T-NNN) | arch | M-NNN | `模块` 字段 + `context_load: arch#§2.M-xxx` | `check_bidirectional_coverage()`（dev-plan→arch M-NNN） FAIL |
| dev-plan (T-NNN) | arch | API-NNN | `接口` 字段 + `context_load: arch#§3.API-xxx` | 无强制检查 |
| dev-plan (T-NNN) | ui-spec | C-NNN / P-NNN | `context_load: ui-spec#§2.C-xxx` | 无强制检查 |
| test-report | dev-plan | T-NNN | 缺陷关联任务 ID、用例矩阵功能列 | QA AGENT.md 要求"按 T-xxx 加载 dev-plan" |
| test-report | arch | API-NNN | 可选加载 `arch#§3.API-xxx` | 可选 |
| deploy-spec | arch | tech-stack（§1.4）, §6, §7 | DevOps 必须加载这三节 | AGENT.md Input Contract |
| dev-plan (T-NNN) 内 AC-NNN | arch | API-NNN 字段名 | `AC literal-reference` 强制逐字复用 arch 定义 | doc-review AI 层检查（无脚本守卫） |

---

## §1.7 SDLC 角色 × 产物映射

### 6 个 SDLC 核心角色（来自 `.cataforge/agents/`）

下表从各 `AGENT.md` 的 `Input Contract` / `Output Contract` 和 `allowed_paths` 字段提取：

| 角色 | 产出文档（写） | 消费文档（读） | 关键实体类型 |
|------|-------------|-------------|------------|
| **product-manager** | `docs/prd/prd-{project}.md`（主卷）；可选 prd-volume 分卷；`docs/brief/brief-{project}.md`（prototype 模式）；`docs/research/*.md` | 用户原始需求（自然语言） | Feature (F-NNN), AC-NNN |
| **architect** | `docs/arch/arch-{project}.md`（主卷）；分卷 arch-modules / arch-api / arch-data；`docs/research/*.md` | prd（§1, §2.F-xxx, §3）→ 按 `cataforge docs load` 加载 | Module (M-NNN), APIContract (API-NNN), Entity (E-NNN)；引用 F-NNN |
| **ui-designer** | `docs/ui-spec/ui-spec-{project}.md`（主卷）；分卷 ui-spec-components / ui-spec-pages；`docs/research/*.md` | prd（§2.F-xxx）, arch（§2.M-xxx, §3.API-xxx）→ 按需加载 | Component (C-NNN), Page (P-NNN)；引用 F-NNN, API-NNN |
| **tech-lead** | `docs/dev-plan/dev-plan-{project}.md`（主卷）；分卷 dev-plan-sprint；`docs/research/*.md` | arch（§2.M-xxx, §3.API-xxx, §6, §7）, ui-spec（§2.C-xxx, §3.P-xxx）→ 按需加载 | Task (T-NNN), AC-NNN（tdd_acceptance）；引用 M-NNN, API-NNN, C-NNN, P-NNN |
| **qa-engineer** | `docs/test-report/test-report-{project}.md` | dev-plan（§2.T-xxx，tdd_acceptance + deliverables）；可选 arch（§3.API-xxx）, ui-spec（§3.P-xxx）→ 按需加载 | TestCase（用例矩阵）；引用 T-NNN, AC-NNN |
| **devops** | `docs/deploy-spec/deploy-spec-{project}.md`；`docs/changelog/changelog-{project}.md` | arch（§1.4, §6, §7）；可选 arch API/Data 分卷，test-report → 按需加载 | 无新实体；消费 tech-stack、环境配置、M-NNN/API-NNN/E-NNN |

### 角色 → 文档 → 实体类型三层映射

```
product-manager → prd            → Feature (F-NNN), AC-NNN
architect       → arch           → Module (M-NNN), APIContract (API-NNN), Entity (E-NNN)
                                   [reads] F-NNN from prd
ui-designer     → ui-spec        → Component (C-NNN), Page (P-NNN)
                                   [reads] F-NNN from prd; API-NNN, M-NNN from arch
tech-lead       → dev-plan       → Task (T-NNN), AC-NNN (tdd_acceptance)
                                   [reads] M-NNN, API-NNN from arch; C-NNN, P-NNN from ui-spec
qa-engineer     → test-report    → TestCase (用例矩阵行)
                                   [reads] T-NNN, AC-NNN from dev-plan
devops          → deploy-spec    → (无新实体，消费 tech-stack)
                + changelog      → 版本条目
                                   [reads] M-NNN context from arch
```

---

## [依赖传递摘要]

**关键决策**:
- 业务文档的核心领域实体已有明确 ID 体系（F/M/API/E/C/P/T-NNN），可直接映射为 KG 节点类型；跨文档引用关系（arch→prd F-NNN、dev-plan→arch M-NNN 等）是 KG 边的主要原始信号。
- 当前唯一机器可读索引 `docs/.doc-index.json` 已有 section/item 的 `line_start`/`line_end`/`est_tokens`/`deps`/`content_hash` 字段；KG 迁移可以此为基础，升级为图存储，无需推翻文件存储层。
- `cataforge docs load` CLI 是 Agent 访问业务文档的唯一规范接口；KG 层需提供兼容的替代后端（或在其之上封装），同时保留 Markdown 导出路径（KG→Markdown 双写/只读导出）。
- 框架资产（`.cataforge/` 下的 SKILL.md/AGENT.md）不纳入业务文档 KG，保持文件系统驻留。
- 当前最严重的结构缺陷是"跨文档语义关系依赖正则/glob 匹配"（假阳性覆盖检查、假阴性 xref 检查），KG 层可用图遍历替代，是最高优先级的正确性收益点。

**输出物路径/位置**: `docs/proposals/kg-migration-0.5.0/task-1-current-system.md`

**阻塞标记**: NONE
