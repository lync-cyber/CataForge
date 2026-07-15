# 提案：CataForge 目录与文件结构重构

> 状态：规划中，未实施。本文为施工蓝图与验收判据，落地以后续各 PR 的 git diff 为准。
> 范围：主 = `src/cataforge/`（判据：分层 import 合法性 + 模块内聚）；次 = `tests/`（判据：镜像 src 子系统）；`.cataforge/` 与 `docs/` 经评估后**刻意不动**（见 §7）。含 `interface/cli/` 子系统专项（§2.3 / §3.2 / §4.2）。
> 依据：实测 `scripts/checks/check_layer_dependencies.py` 秩表与治理面、各模块 import 关系、`docs/.docignore` 排除规则；结论均附证据路径。
> 交付边界：现状诊断、目标目录树、变更映射、迁移序、权衡为本文职责；实施代码以后续 PR 为准。**不含工时估算**，成本一律以维度（单点 / 多文件 / 需跨包重构）表达。

---

## 0. 一句话

物理结构总体健康，真正的结构债集中在**两处 grab-bag**（`utils/common.py`、`interface/cli/` 根平铺）外加 **tests 根 16 个裸测试未归位**。据此做「拆 grab-bag + 裸测试归位 + 一处巨型命令按先例子包化」的最小可行重排——全程在分层最安全区（同层 / 下行）内完成，不制造任何上行 import。

---

## 1. 不可违反的前提（本仓真实约束）

1. **分层方向**由 `scripts/checks/check_layer_dependencies.py` 强制。秩（越小越"驱动"，只能 import 秩 ≥ 自己的层）：
   `interface(0) → application(1) → {runtime(2), domain(2)} → adapter(3) → core(4) → utils(5)`（`check_layer_dependencies.py:45-53`）。
2. **守卫只治理**顶层目录名 ∈ `LAYER_RANK` 的包（`check_layer_dependencies.py:167`）。**任何不在这 7 个层名里的顶层目录会被整包跳过、完全不受治理** —— 这是 §6 否决「viz 聚合为顶层包」的决定性依据。
3. `UPWARD_IMPORT_ALLOWLIST`（`check_layer_dependencies.py:67-102`）登记 5 条 lazy/TYPE_CHECKING 上行例外，锚定具体文件路径。本方案的移动集**不触及**任何锚点文件，故 allowlist 无需改动。
4. `.cataforge/` 的 SKILL/AGENT/rules 受 `check_no_language_coupling` / `check_no_design_residue` / `check_doc_structure` 治理；本方案不动这些文件，**不触发**。
5. `docs/.docignore` 已排除 `proposals/`（含本文件）——proposals 不在 doc-index orphan 检查面内、无需 YAML front-matter、移动/新增**不需要 `cataforge context index` 重建**。`docs/.doc-index.json` 本身为 gitignore 生成物（`.gitignore:215,240`）。
6. 落地以 `uv run --extra dev python scripts/checks/run_local.py` 全绿为准。

---

## 2. 现状诊断

### 2.1 分层守卫硬事实

`interface` 是 rank 0，可 import 任何层；`adapter(3)` 位于 `runtime/domain(2)` **之下**（外部集成比运行时机制更基础）；`core(4)` / `utils(5)` 为最基础原语。因此：**任何 `interface/` 内部或向下的移动都不触发 layer-dep 守卫**，CLI 子系统是分层最安全的重排区。

### 2.2 候选张力逐条结论

**① viz 散落 `core/viz` 与 `application/viz` —— 可接受 / 刻意分层，聚合被守卫机制否决。**

- `core/viz/`（`model.py` / `palette.py` / `render/{dot,json_,mermaid}.py`）是纯 IR + 文本渲染器，仅自引用、stdlib-only（`core/viz/__init__.py:1-7`）。
- `application/viz/`（`collectors/*` / `html/*` / `service.py` / `portfolio.py` / `registry.py` / `snapshots.py`）是触达数据源的采集器 + HTTP serve 编排（`application/viz/service.py:24-31` import KG/docs/event-log/corrections）。
- 「纯内核（低层）/ 有副作用编排（高层）」切分，非错层。实测 `core.viz` 消费者仅 `interface/cli/viz_cmd.py`(0) 与 `application/viz/*`(1)，**无 runtime 消费者** —— `core/viz/__init__.py` 提到「runtime … call-sites」为陈旧注释（唯一可动项、注释级、不在结构重构内）。
- **聚合为单一顶层 `cataforge/viz/` 不可行**：`viz` 不在 `LAYER_RANK`，守卫整包跳过 → viz 变成不受分层治理的孤岛，比现状更差。

**② `utils/` 退化为杂物抽屉 —— 真问题，限于 `common.py` 一个文件，需拆解。**

- `utils/common.py`（270 行）塞了 5 类互不相干职责：ANSI 颜色常量 + `section/info/ok/warn/fail` 控制台代理（`:25-63`）、`ensure_utf8` 编码引导（`:76-147`）、`has_command/run_cmd/get_command_version` 进程助手（`:155-181`）、`detect_platform` OS 探测（`:189-195`）、网络 `is_port_listening/check_port_available/find_available_port` + `load_dotenv`（`:203-269`）。
- 同目录 `process.py` / `console.py` / `run_subprocess.py` / `md_parse.py` / `placeholders.py` 均单一职责 —— 问题**只在 `common.py`**，非整个 utils/。
- `utils/patterns.py` 内容内聚（markdown 文档解析正则），但消费者仅 `domain/docs/` 4 文件（`_index_build.py` / `index_ops.py` / `indexer.py` / `loader.py`），且其正则（`REF_RE` = `doc_id#§section`、`ITEM_ID_RE` = `F-001`）编码 CataForge 文档模型领域词汇 —— 属领域逻辑轻度滞留 utils。

**③ core 与 domain 边界 —— 可接受（边界可辩护），无强制移动。**

- `domain/` = 两个富状态领域模型（`docs/` 文档索引、`kg/` 知识图谱，共 56 文件）；`core/` = 领域无关原语 + 框架级词汇常量。
- `core/phases.py`（SDLC 词汇常量，`:1-7` 自述「any layer may import it downward」）与 `application/phase.py`（`evaluate_phase` 评估服务）是干净的「词汇/服务」二分，非重复。命名近似（phases vs phase）是轻微可发现性噪音，分层正确。
- `core/corrections.py` 实测层级可移（消费者秩 0/1/2，无 core/utils 上行者），但 §6 予以否决保留（与 `core.event_log` 紧耦合、`CORRECTIONS_LOG_REL` 为广泛 import 的路径常量）。

**④ runtime/domain 同 rank(2) + adapter 归属 —— 一致。**

- 外部集成归属统一：penpot→`adapter/integrations`；codex/claude_code/cursor/opencode→`adapter/platform`。
- `runtime/mcp/` 管 MCP 进程生命周期（机制），非某一外部系统适配，留 runtime 合理。MCP 关注点跨 `core/schema/mcp_spec.py` + `adapter/platform/mcp_config.py` + `runtime/mcp/` + `runtime/deploy/steps/mcp.py`，每片各归其层，是协议横切的必然。
- 唯二摩擦（`adapter/platform/{cursor,opencode}.py` 的 TYPE_CHECKING 上行）已在 allowlist 显式登记。

**⑤ tests 根 16 个裸 `test_*.py` —— 真问题，需归位。**

实测两类（`find tests -maxdepth 1 -name 'test_*.py'`）：

- **3 个 utf8 行为测试** → 归 `tests/utils/`：`test_ensure_utf8_relaunch.py` / `test_run_utf8.py` / `test_conftest_utf8_reexec.py`。
- **13 个仓库守卫/契约测试**（靶向 `scripts/checks/*` 与跨切面不变量，不对应单一 src 子系统）→ 归新建 `tests/guards/`：`test_anti_rot_guards` / `test_check_doc_authoring_invariant` / `test_check_echo_err_for_errors` / `test_check_migration_notes_version` / `test_check_orphan_cli_capabilities` / `test_check_profile_version_tested` / `test_check_prompt_cli_drift` / `test_framework_constants_ssot` / `test_project_state_hygiene_contract` / `test_prompt_section_name_consistency` / `test_runtime_dependency_contract` / `test_scripts_stdio_guard` / `test_stdin_read_guard`。

**⑥ tests 是否镜像 src 子系统 —— 基本镜像（按子系统扁平，非按层），1 处缺口。**

- 现有映射清晰：`cli`→interface/cli、`agent/deploy/hook/mcp/plugin/skill`→runtime/*、`context/services/unattended`→application/*、`kg`→domain/kg、`integrations/platform`→adapter/*、`schema`→core/schema、`core`→core、`utils`→utils。符合「同一子系统测试聚拢、不追求逐层同构」。
- **缺口**：无 `tests/viz/`。`application/viz`（约 15 文件）仅经 `tests/cli/test_viz_cmd.py` + `tests/e2e/test_viz_*` 间接覆盖，无采集器/service 单元测试目录。`domain/docs` 单测寄居 `tests/cli/test_docs_*`（测的是 `cataforge docs` CLI，属 CLI 级，可接受）。

### 2.3 `interface/cli/` 子系统专项诊断

`cli/` 根平铺 **34 个文件**，混三类：

- **命令入口**：23 个 `*_cmd.py`（+ `doctor/`、`kg/` 两个已子包化的命令组）。
- **CLI 基础设施**（9 个、约 1038 行，实测 cli 外部引用≈0）：`ui.py`(453) `doc_io.py`(236) `helpers.py`(109) `diagnostics.py`(73) `guidance.py`(63) `guards.py`(48) `errors.py`(28, 唯一 1 处 cli 外部引用) `stubs.py`(21) `_hints.py`(7)。
- **装配**：`main.py`（`_register_commands()` 通过 import 副作用触发 Click 注册，`main.py:147-178`）。

**问题 A（可发现性）**：命令入口与基础设施平铺，`ls cli/` 一眼分不清命令 / 设施。

**问题 B（子包化门槛）**：已有 `doctor/`、`kg/` 两个子包，但巨型命令仍平铺。逐个实测装配点后修正判据：

| 命令文件 | 行数 | 子命令实质 | 结论 |
| --- | --- | --- | --- |
| `context_cmd.py` | 668 | 16 子命令，中等密度（~42 行/命令） | **子包化候选**（需先验证可归 4–6 命令族） |
| `feedback_cmd.py` | 589 | 5 子命令 | 次级候选，5 命令收益中等，暂缓 |
| `setup_cmd.py` | 539 | 4 子命令 | 次级候选，暂缓 |
| `viz_cmd.py` | 340 | 1 组 + 13 **极薄委托**子命令（~15 行/命令，逻辑全在 `application/viz`） | **否决**，拆成 13 tiny 文件属过度碎片化 |
| `bootstrap_cmd.py` | 414 | 1 命令 | **否决**，单命令、长是函数问题非结构问题 |

**两种子包模式并存，非不一致**：`doctor` 是「单命令聚合多检查」（`doctor_cmd.py` 的 `@cli.command("doctor")` + `doctor/` 实现子包）；`kg` 是「命令组含多子命令」（`kg/__init__.py` 的 `@cli.group("kg")` + `from . import …`，docstring 自述「Command families (one module each)」，把 ~17 子命令收敛成 5 个 family 模块）。二者面对的结构不同，各自恰当，**不需统一**。

**守卫爆炸半径（实测）**：`check_orphan_cli_capabilities.py` / `check_prompt_cli_drift.py` introspect Click 树、按**命令名**判定，**不依赖文件路径**。只要命令名不变、`_register_commands()` import 到位，命令文件重命名/移动**不触发**这两个守卫。

### 2.4 额外发现

- **application 顶层散文件**：`application/phase.py`、`application/unattended_preflight.py` 直挂 `application/`，而 `context/`/`feedback/`/`services/`/`viz/` 为子包。轻微不一致，但 `application.phase` 是 allowlist 锚点（`check_layer_dependencies.py:90-93`），移动波及守卫、低收益，**不动**（§6）。

---

## 3. 目标结构

只画发生变更的区域；未列出目录保持原样。跨层移动处标注「移动后 import 方向核对」。

### 3.1 `src/cataforge/`

```
src/cataforge/
├── utils/                          # rank 5 —— 解散 grab-bag
│   ├── encoding.py        [新]     # ← common.ensure_utf8 + _preferred_encoding_is_utf8
│   │                               #   （最高频导出 ~15 处跨层调用，独立成模；utils→utils 无跨层）
│   ├── console.py         [并入]   # ← 收编 common 的 section/info/ok/warn/fail + ANSI 常量
│   ├── process.py         [并入]   # ← 收编 common.has_command/run_cmd/get_command_version/
│   │                               #   detect_platform（消费者含 adapter/platform/registry、
│   │                               #   runtime/hook/lint_format，非 penpot 专有，留 utils）
│   ├── patterns.py        [可选移出 → domain/docs/patterns.py]  # 见 §4.1 E
│   └── common.py          [删]     # 掏空后删除
│
├── adapter/integrations/penpot/    # rank 3
│   └── netenv.py          [新]     # ← common 的 is_port_listening/check_port_available/
│                                   #   find_available_port + load_dotenv（实测仅 penpot + penpot_cmd 消费）
│                                   #   ▸ import 核对：adapter(3) 不新增上行；原 penpot→utils.common 转为
│                                   #     penpot 内部；interface/penpot_cmd(0)→adapter(3) 早存在，合法 ✓
│
├── core/viz/                       # rank 4 —— 结构不动（聚合被守卫机制否决，§2.2①）
└── application/viz/                # rank 1 —— 不动
```

### 3.2 `interface/cli/`

```
interface/cli/
├── main.py                         # 装配，保留根
├── _support/              [新]     # CLI 内部基础设施（下划线前缀=非命令、内部）
│   ├── ui.py  doc_io.py  helpers.py  diagnostics.py
│   ├── guidance.py  guards.py  errors.py  stubs.py  _hints.py
│   └── __init__.py                 # ▸ import 核对：interface 内部同层移动，不触发 layer-dep ✓
├── context/              [候选]    # ← context_cmd.py 按 kg「命令族」模式子包化（须先验证可归族）
│   └── __init__.py（装配 @cli.group）+ 按族分模块
├── doctor_cmd.py + doctor/         # 现状保留（单命令 + 实现子包）
├── kg/                             # 现状保留（命令组 + 子命令子包）
└── *_cmd.py …                      # 其余命令入口；根目录一眼皆命令
```

### 3.3 `tests/`

```
tests/
├── guards/                [新]     # ← 13 个守卫/契约裸文件（§2.2⑤）
│   └── __init__.py        [新]
├── utils/                          # ← 3 个 utf8 裸文件移入（§2.2⑤）
└── viz/                   [新·可选]# application/viz 采集器/service 单元测试归位目标（§2.2⑥缺口）
                                   #   仅当后续新增/迁移 viz 单测时启用，不强制现建空目录
```

---

## 4. 变更映射

标出破坏 import / 触发守卫的项。interface rank 0 → `cli/` 内部移动一律不触发 layer-dep。

### 4.1 `src/cataforge/`

| # | old → new | 操作 | 原因 | import / 守卫连带 |
| --- | --- | --- | --- | --- |
| A | `utils/common.py`（`ensure_utf8`,`_preferred_encoding_is_utf8`）→ `utils/encoding.py` | 拆分 | 最高频导出独立成模 | 更新 ~15 处 import；utils→utils 无 layer 变化；ruff 兜底 |
| B | `utils/common.py`（`is_port_listening`,`check_port_available`,`find_available_port`,`load_dotenv`）→ `adapter/integrations/penpot/netenv.py` | 移动（下沉） | 实测仅 penpot + `interface/cli/penpot_cmd.py` 消费 | 更新 penpot 4 文件 + `penpot_cmd.py`；**触发 `check_layer_dependencies`**：adapter 不新增上行、interface(0)→adapter(3) 合法 ✓ |
| C1 | `utils/common.py`（`has_command`,`run_cmd`,`get_command_version`,`detect_platform`）→ `utils/process.py` | 并入 | OS/进程助手跨 adapter/runtime，留 utils | 更新 `adapter/platform/{registry,__init__}`、`runtime/hook/scripts/lint_format`、`utils/docker_util`、penpot；utils→utils 无跨层 |
| C2 | `utils/common.py`（`section/info/ok/warn/fail` + ANSI 常量）→ `utils/console.py` | 并入 | 与其代理的 `get_console()` 端口就近同置 | 更新各 import；utils→utils 无跨层 |
| D | `utils/common.py` → 删 | 删除 | A–C 掏空后无残留 | 确认全仓无 `utils.common` 残留引用后删；run_local 校验 |
| E | `utils/patterns.py` → `domain/docs/patterns.py` | 移动（**可选**） | CataForge 文档模型正则、消费者仅 domain/docs 4 文件 | 更新 4 处 import；**触发 `check_layer_dependencies`**：domain(2)→domain(2) 合法，消除一条 domain→utils(5) 跨层 ✓ |

### 4.2 `interface/cli/`

| # | old → new | 操作 | 原因 | import / 守卫连带 |
|---|---|---|---|---|
| G | `cli/{ui,doc_io,helpers,diagnostics,guidance,guards,errors,stubs,_hints}.py` → `cli/_support/` | 移动 | 分离基础设施与命令入口，提升可发现性 | 更新 cli 内部各 import + `main.py:34` 的 `errors.CataforgeGroup` + `errors` 的 1 处外部引用 + `tests/cli` 中 `cli.helpers` import；interface 内部同层、**不触发 layer-dep**；命令名不变、**不触发 CLI 守卫** |
| H | `cli/context_cmd.py` → `cli/context/`（`__init__.py` 装配 + 命令族模块）| 拆分（**候选**） | 668 行/16 子命令，最大命令文件 | **前置**：须先验证 16 子命令可归 4–6 族（仿 kg），否则不拆；`main.py:157` `_register_commands()` 的 `context_cmd` 改为 `context`；`tests/cli/test_context_*` 中 `context_cmd.context_read` 等深路径 import 连带；不触发 layer-dep / CLI 守卫 |

### 4.3 `tests/`

| # | old → new | 操作 | 原因 | 连带 |
| --- | --- | --- | --- | --- |
| F1 | `tests/test_{ensure_utf8_relaunch,run_utf8,conftest_utf8_reexec}.py` → `tests/utils/` | 移动 | utf8 行为归 utils 子系统 | 无 src import 影响；仅 pytest 发现路径；**验证文件内无 repo-root 相对路径假设** |
| F2 | 13 个守卫/契约裸文件（§2.2⑤清单）→ `tests/guards/` | 移动 | 守卫/契约测试聚拢、清空 tests 根 | 新增 `tests/guards/__init__.py`；确认 `tests/conftest.py` 顶层作用域仍覆盖；**验证被移测试对 `scripts/checks/` 的路径引用不依赖自身目录** |

> **未受影响的守卫**：`check_no_language_coupling` / `check_no_design_residue` / `check_doc_structure` 只作用于 `.cataforge/` SKILL/AGENT/rules，本方案不动这些文件、**不触发**。`UPWARD_IMPORT_ALLOWLIST` 的 5 条路径锚点均不在移动集内，**无需改动**。

---

## 5. 迁移顺序（依赖 + 守卫安全落地，分 PR）

原则：被依赖者先行；每步独立 PR，conventional-commits 标题、squash merge，`uv run --extra dev python scripts/checks/run_local.py` 全绿 + 全量 `uv run pytest -n auto --dist loadscope`。utils 各拆分互不依赖，可并行但建议串行以降 rebase 噪音。

1. **`refactor(utils): extract ensure_utf8 into encoding module`**（映射 A）—— 最高频、纯 utils 内移动，先锁定收益。
2. **`refactor(penpot): sink port/dotenv helpers into penpot netenv`**（映射 B）—— 必跑 `check_layer_dependencies` 确认 adapter 无新增上行。
3. **`refactor(utils): fold process/console helpers, drop common grab-bag`**（映射 C1+C2+D 合一）—— 同 PR 完成「并入 + 删源」避免中间态双定义；run_local 确认无 `utils.common` 残留。
4. **`refactor(cli): move shared cli infra into _support subpackage`**（映射 G）—— 收益即时、风险最低的 CLI 改动；全量 pytest 确认 Click 注册无碍。
5. **`refactor(tests): group guard and utf8 tests out of tests root`**（映射 F1+F2）—— 纯测试重排，不改 src。
6. **（可选）`refactor(cli): split context command into family modules`**（映射 H）—— **先验证 16 子命令可归族**，可归则做、归不出则放弃。
7. **（可选）`refactor(domain): relocate doc-model regex patterns into domain/docs`**（映射 E）—— 收益最低，最后做。

> **docs / .cataforge 无迁移步骤**：本方案零改动，无需 `cataforge context index`（proposals 被 docignore 排除、doc-index 为 gitignore 生成物），不触及 `docs/reviews` front-matter 契约与 deploy 的 `.cataforge/{skills,agents,rules}`→`.claude/` 镜像（无目录改名 → junction/symlink 目标不变）。

---

## 6. 权衡与风险

**被否决的备选组织方式：**

- **viz 聚合为顶层 `cataforge/viz/`**：守卫只治理 7 个层名目录，`viz/` 会被整包跳过 → 逃逸分层治理，比现状更差（§2.2①）。
- **`core/viz` 上并入 `application/viz`**（利用「无 runtime 消费者」使其层级合法）：会把纯 IR/渲染内核与有副作用采集器混同层，丧失「纯内核不可上行 import」这一由分层自动强制的纯度保证。保留 core/viz 的唯一代价是 `__init__.py` 一句陈旧注释，应以注释修正而非结构迁移解决。
- **`core/corrections.py` 上移 domain/**：虽层级可移，但它本质是 `core.event_log` 的「事件 + 人类 markdown 镜像」薄写入器，与 event_log 紧耦合同置 core 更内聚；`CORRECTIONS_LOG_REL` 是广泛 import 的路径常量。上移只换边际语义整洁，却把两个耦合写入器劈到两层。
- **`utils/patterns.py` 强制移 domain**：降级为可选（步骤 7）。「通用文本正则留 utils」亦可辩护，收益低于前几步，不阻塞主线。
- **`application/phase.py` 归 services/**：它是 allowlist 锚点（`check_layer_dependencies.py:90-93`），移动需连改 allowlist，且顶层可见性本无问题 —— 低收益、有守卫连带，不做。
- **`viz_cmd.py` / `bootstrap_cmd.py` 子包化**：viz 是 13 薄委托子命令（碎片化），bootstrap 是单命令（函数级问题），均否决（§2.3）。
- **统一 doctor / kg 两种子包模式**：二者面对结构本不同（单命令+实现子包 vs 命令组+子命令子包），各自恰当，强行统一反而错。

**刻意不动的部分：** 见 §7。

**残余风险与缓解：**

- 拆 `common.py` / 移 CLI 文件的唯一实质风险是**漏改 import** → `run_local.py`（ruff F401/undefined）与全量 pytest 双重兜底（成本维度：多文件、机械式）。
- 步骤 5 移测试的**路径假设风险**（守卫契约测试或硬编码相对路径）→ 移动前 grep 每个被移文件对 `Path(__file__)` / repo-root 的推导，逐个确认（成本维度：单点核查）。
- 步骤 2 下沉 penpot 的**层级风险**由 `check_layer_dependencies` 在 PR 内即时拦截，不会漏网。

---

## 7. 刻意不动的分区

- **`.cataforge/`（skills/agents/rules/references）**：判据是「prompt 加载成本 + 可发现性」。实测已普遍采用 `references/` 子目录的 token-lazy 模式（12/28 skill 有 `references/`）。任何改名/加深会①增加每次调度加载量或②破坏 deploy 的 per-skill 镜像目标，高爆炸半径、零结构收益。保持现状即最优。
- **`docs/`**：判据是「可发现性 + 契约不破」。已按 architecture/guide/reference/proposals/reviews 清晰分区；`doc-index` 为 gitignore 生成物；`docs/reviews` 有 front-matter 契约。无错位，移动只会平白触发风险。
- **`runtime/skill/builtins/` 深层树**：各 builtin 高内聚（一 skill 一子包），无 grab-bag 征兆。
- **MCP 跨 core/adapter/runtime 的分散**：每片各归其层，是协议横切的必然，非事故。

---

## 8. 总成本画像

主线（步骤 1–5）为**多文件机械式**改动，无跨包架构重构；步骤 6–7 为**单点可选**。全程不制造上行 import、不触碰 allowlist、不改 `.cataforge/` / `docs/`，落地风险集中在「import 补全」这一由现有门禁完全覆盖的类别。
