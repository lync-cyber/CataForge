# CataForge 阶段性重构方案（Python 架构与技术债治理）

> 范围：`src/cataforge/`（266 源文件 / ~40k 行）+ `tests/`（219 文件 / 1860 用例）。
> 方法：4 路并行证据驱动审计（分层耦合 / 类型契约 / 死代码重复 / 测试现状）+ 工具核查（ruff C901、mypy、AST import 图）。
> 关联前序工作：`docs/proposals/framework-audit-2026-05/`（26 条，聚焦**框架机制正确性**：死守卫 / SSOT 漂移 / 部署漂移 / 自审盲区）。本方案聚焦**Python 架构与代码质量**维度，与之互补，仅在死代码处交叉引用 R-006。

---

## 0. 总体判断

CataForge **不是**需要推倒重来的项目。它已具备同规模项目少见的工程纪律：

- 清晰的六边形分层：`interface → application → {runtime, domain} → adapter → core → utils`
- 18 个自定义静态守卫（`scripts/checks/check_*.py`）+ pre-commit + per-PR CI
- ruff 全绿（`E F I N W UP B SIM C901`，line-length 100）
- 按包 opt-in 的 mypy strict（已落地 `application.services.*` 零错误）
- facade（`domain/kg/facade.py`）、Strategy（`PlatformAdapter` ABC + 4 实现）、Registry、Ports/Adapters（`application/context/ports.py`）等模式运用得当

**核心问题不在静态结构，而在一张被守卫豁免规则掩盖的"影子依赖图"**：`check_layer_dependencies.py` 显式豁免 `TYPE_CHECKING` 块、函数体内延迟 import 与 `# allow-layer-dep`，导致守卫报 `OK: layered dependency direction clean` 的同时，存在 **27 处真实反向依赖** 与 **283 处函数内延迟 `cataforge` import**。这把"依赖方向单向向下"从一条被强制的不变量，降级成了一条被普遍绕过的口号。

因此本次重构定性为：**定向技术债治理 + 收敛被绕过的分层契约**，而非架构 teardown。下面八节逐项展开。

### 0.1 决策记录（2026-06，已拍板）

§8 原"待澄清硬边界"已逐项决策，全文按此推进：

| 决策项 | 结论 | 涟漪影响 |
|--------|------|---------|
| **向后兼容基线** | **全部可自由重构**——CLI 命令面、deploy 产物布局、`DeployManifest` 磁盘格式、内部 Python 模块（`core.*`/`domain.kg.nl_query` 等）**均视为非契约**，假设无 in-the-wild 已部署项目静默升级场景，追求最干净结构 | 模块迁移**无需 re-export shim**；`DeployManifest` 格式可有意变更；D-9（`nl_query`）由"需确认"转为**可删**；G2 不必保留旧 mixin 过渡版本 |
| **profile/hooks 建模** | **pydantic**——`PlatformProfile`/`HookEntry` 用 pydantic BaseModel，profile.yaml 获**加载期强校验**，畸形配置从运行时错误前移到加载期 | G5 改动 1/2 落 pydantic；需为加载期校验新增容错回归测试（畸形 profile→清晰错误信息）；与既有 `core/schema/mcp_spec.py` 的 pydantic 用法一致 |
| **最低 Python 版本** | **≥3.11**（`requires-python` `>=3.10` → `>=3.11`）——放弃 3.10 用户 | 可用 `tomllib` 读取 codex TOML 配置、`typing.Self` 简化链式返回、异常组等；CI matrix 去掉 3.10；classifiers 去 3.10 |
| **阶段 5（deploy 收回 runtime）** | **全量迁移**——deploy 算法物理迁回 `runtime/deploy/steps/`，adapter 降为纯 config/capability carrier，彻底消除 adapter↔runtime 反向边（L-4/C-2/L-6） | 仍作为 `pre_dev` 检查点单独 go/no-go；验证以 e2e deploy→doctor 通过 + 四端 dry-run 结构对比为准（manifest 不再要求字节兼容） |

---

## 1. 现状评估

格式：【位置 / 问题 / 严重度 / 影响】。严重度沿用 `CRITICAL/HIGH/MEDIUM/LOW`（COMMON-RULES §统一问题分类体系）。

### 1.1 包与模块结构

| ID | 位置 | 问题 | 严重度 | 影响 |
|----|------|------|--------|------|
| S-1 | `adapter/integrations/penpot/__init__.py`（522 行） | 14 个 `cmd_*` 命令处理器 + `get_config()` + UI 渲染 + 诊断逻辑全部塞进包初始化文件，`__init__.py` 承载实质业务逻辑而非 re-export | HIGH | import `penpot` 即执行全部定义；命令、配置、UI、诊断四个关注点无法独立测试或复用 |
| S-2 | `adapter/platform/helpers.py`（594 行 / 21 函数） | 单文件混合三个不相关关注点：文件操作（symlink/copy/prune ~285 行）、hooks 配置合并（~75 行）、MCP 配置序列化（~170 行） | MEDIUM | 任一关注点变更都要打开 594 行的大文件；文件操作部分是平台无关通用工具却埋在 platform 包内 |
| S-3 | `runtime/mcp/lifecycle.py`（597 行） | `MCPLifecycleManager`（12 方法）混合进程生命周期、3 种健康探测协议、JSON 状态持久化；模块级另有 165 行进程工具（`pid_alive`/`_pid_alive_windows`/spawn lock） | MEDIUM | `pid_alive` 是纯 OS 原语却被 `adapter/penpot` 用 `allow-layer-dep` 跨层借用（见 L-7） |
| S-4 | `core/scaffold.py`（555 行 / 18 函数） | 混合资源解析、scaffold 复制+manifest、备份/恢复三组职责 | LOW | 备份/恢复（8 函数 ~130 行）可独立；关联度尚可，非紧急 |
| S-5 | 全代码库 | **283 处函数内延迟 `cataforge` import**（`cli/kg/ingest.py` 14、`deploy/deployer.py` 12、`upgrade_cmd.py`/`setup_cmd.py`/`bootstrap_cmd.py` 各 11…） | HIGH | 真实依赖图对静态分析不可见；多数是为规避 import 环而非性能优化，是潜在循环依赖的征兆 |

`interface/cli/main.py` 为对照正例：薄入口，命令经 import 副作用注册，无逻辑下沉。`__init__.py` 中 `framework_review`/`doc_review`/`code_review` 的大体量是合法的 `CHECKS_MANIFEST` 常量声明，非违规。

### 1.2 分层与边界（核心问题域）

守卫盲区导致的 **27 处反向依赖**，按危害排序：

| ID | 位置 | 反向边 | 严重度 | 影响 |
|----|------|--------|--------|------|
| L-1 | `utils/common.py:44-68` | **utils(5) → interface(0)** | HIGH | `section/info/ok/warn/fail` 5 个包装函数延迟 import `interface.cli.ui`——最底层绑定最顶层，跨满栈倒置。任何用 `utils.common` 的 hook 脚本/集成都会拉入 Click+UI 渲染链，无法在无 CLI 环境独立运行 |
| L-2 | `core/feedback/collectors.py:106,253` | **core(4) → application(1) / runtime(2)** | HIGH | `collect_doctor_summary()` 穿透 core→application→interface 三层（docstring 自承为规避 import 环）；`collect_framework_review()` → `runtime.skill.runner`。`core.feedback` 整包无法脱离完整 CLI 栈测试 |
| L-3 | `adapter/integrations/penpot/__init__.py:340`、`mcp_process.py:177` | **adapter(3) → interface(0)** | HIGH | penpot 调用 `interface.cli.ui.ChoiceOption`/`ui` 做交互提示、引用 `interface.cli.diagnostics.PENPOT_PATTERNS` 做日志诊断——penpot 自己的诊断模式数据被放到了 interface 层 |
| L-4 | `adapter/platform/_deploy_mixins/agents.py:138,277` | **adapter(3) → runtime(2)** | MEDIUM | deploy mixin 延迟 import `runtime.agent.translator`；叠加 9 处 `DeployManifest` 的 TYPE_CHECKING import，形成 `runtime.deploy.deployer → adapter → runtime.agent/deploy` 的设计循环（懒加载规避了静态死锁，但逻辑环真实存在） |
| L-5 | `application/services/bootstrap.py:140`、`doctor_summary.py:31` | **application(1) → interface(0)** | MEDIUM | `bootstrap` 借用 interface 的 `classify_tallies`（纯 Counter 聚合，与 CLI 无关）；`doctor_summary` 用 Click `CliRunner` 在 application 层内嵌 interface 执行机制反向驱动 CLI |
| L-6 | `core/template.py:30` | **core(4) → adapter(3)** | MEDIUM | `render_runtime_content(adapter: PlatformAdapter)` 是 adapter 关注点（把平台 token 替换进 markdown），却住在 core；调用方全在 `adapter/_deploy_mixins/` |
| L-7 | `runtime/mcp/lifecycle.py:165` | adapter 经 `allow-layer-dep` 借用 | MEDIUM | `pid_alive` OS 原语放在 runtime，被 `adapter/penpot/mcp_process.py:23` 跨层引用，已不得不挂 escape hatch |
| L-8 | `doc_review/checker.py:321-354`、`doc_consistency/checker.py:81-111` | runtime → domain **私有**模块 | MEDIUM | runtime checker 直接 import `domain.kg._dispatch`/`._sparql_utils`（带下划线私有）而非 `domain.kg` facade，破坏封装；facade 形同虚设 |
| L-9 | `interface/cli/helpers.py:28` ↔ `main.py:143-168` | interface 内部引用环 | LOW | helpers（工具包）反向依赖 main（入口点），靠 Python partial-module 机制不死锁 |

扇入异常：`interface.cli.ui` 扇入 **28**（含 adapter/utils 跨层），`interface.cli.helpers` 扇入 26（含 application 跨层）——顶层模块被多个下层消费，是 L-1/L-3/L-5 的量化体现。

### 1.3 耦合与抽象

| ID | 位置 | 问题 | 严重度 | 影响 |
|----|------|------|--------|------|
| C-1 | `runtime/deploy/deployer.py:67-245` | `Deployer._deploy()` 单方法 179 行，串接 7 个部署关注点（自愈/override/agent/instruction/hooks/skills/commands/MCP/降级），8 处 `adapter.deploy_*` + 条件判断 + manifest 管理耦合 | MEDIUM | 圈复杂度 ~12；每新增一类部署资产都要改 `_deploy()`，违反 OCP；7 处 lazy import 散落各方法 |
| C-2 | `adapter/platform/_deploy_mixins/*` ↔ `runtime/deploy/` | deploy **算法**（agents/skills/instructions/commands_rules/mcp）住在 adapter 层，但依赖 runtime 的 `DeployManifest`/`translate_agent_md`；adapter 实为"做 runtime 的活" | MEDIUM | 部署关注点跨两层双向耦合，是 L-4 的结构根因 |
| C-3 | `adapter/platform/adapter.py:26` | `PlatformAdapter` 通过多重继承组合 5 个 deploy mixin——mixin 在自身体内调 `self._profile` 等却无契约声明（template-method via mixin，非显式接口） | LOW | 设计可用但隐式；mixin 与宿主类契约不在类型层表达（与 T-3 同类问题） |

抽象正例：ABC/Protocol 分工清晰——`PlatformAdapter`（ABC，运行时多态分发）、`ContextBackend/ContextReadPort/RelationPort`（`runtime_checkable` Protocol，IO 解耦）、`KGQueryPort/KGReadPort`（docs↔kg 边界）。4 个平台实现均完整实现抽象方法，无接口缺失。

### 1.4 类型与契约

| ID | 位置 | 问题 | 严重度 | 影响 |
|----|------|------|--------|------|
| T-1 | `adapter/platform/adapter.py:36` 及 20+ 属性 | `profile: dict[str, Any]`——整个 adapter 体系的配置载体用裸 dict，profile.yaml 结构完全已知（`tool_map`/`hooks`/`model_routing`/`agent_config`/`features`…）却无类型模型 | HIGH | 所有 `.get()` 无类型保护；字段拼写错误/结构漂移到运行时才暴露。`dict[str,Any]` 全库 158 处，此为最大单点 |
| T-2 | `runtime/hook/bridge.py:74,81,85…` | `HookGenerationResult.hooks`、`load_hooks_spec()` 返回 `dict[str,Any]`；hooks.yaml 有 schema_version 受控的固定结构 | HIGH | hook bridge 是跨平台部署核心路径，key 拼写错误测试期无法静态捕获 |
| T-3 | `doc_review/typed_checks.py:59`、`doc_consistency/_checks.py:14` | `TypedDocChecksMixin`/`_CrossDocChecksMixin` 在自身方法体访问 `self.volume_type`/`self.fail()`/`self._content`/`self._issue()` 等**未在 mixin 声明**的属性 | HIGH | mypy 报 **122 个 `attr-defined`** 错误（77+45）；新子类漏属性静态工具无法检测；mixin 契约缺失 |
| T-4 | `application/context/ports.py:43` & `backends.py:39` vs `domain/docs/loader.py:214` | `file_cache: dict[str,Any]`（Protocol/adapter 层）与 `dict[str,list[str]]`（domain 层）不一致，宽窄类型跨层直传 | MEDIUM | 类型检查器无法捕获错误类型 cache 被传入 |
| T-5 | `interface/cli/kg/query.py:118,121,138,238,240,243` | 6 处 `type: ignore` 已失效（`[unused-ignore]`），掩盖真实 `attr-defined` | MEDIUM | 注释掩盖的真实问题仍在 |
| T-6 | `interface/cli/doctor_cmd.py:159` | `failed_count += result` 实为 `int + (int|None)`，`_DOCTOR_SECTIONS` 混合返回 `int` 的 check 与返回 `None` 的 report 且无类型标注 | MEDIUM | doctor 退出码计算类型层面无保障 |
| T-7 | `interface/cli/helpers.py:34` | `get_config_manager()` 无返回类型注解，11 处 typed 调用方触发 `no-untyped-call` | MEDIUM | 类型断点向上游扩散 |
| T-8 | 全局 | mypy **458 错 / 96 文件**（`_generated` 占 80 → 真实 ~378）；strict 与非 strict 错误数相同，说明大头在未进 strict 覆盖的包 | MEDIUM | 类型债集中：`doc_review`(83)/`doc_consistency`(51)/`domain.kg`(42)/`interface.cli.kg`(41) |
| T-9 | `core/event_log.py:155` `build_record()`、`runtime/mcp/registry.py:186` `get_platform_config()` | 返回 `dict[str,Any]`，字段固定可升 TypedDict（event-log 已有运行时 `validate_record` 兜底） | LOW | 运行时有 guard，静态层缺位 |

### 1.5 Pythonic 与代码质量

| ID | 位置 | 问题 | 严重度 | 影响 |
|----|------|------|--------|------|
| Q-1 | `runtime/hook/base.py:120,129,252,369` 等 | 76 处 `except Exception` 中多处 `pass`/`return None`/`continue` 无任何日志（hook/base 与 kg/docs 降级路径尤甚） | MEDIUM | 静默吞异常损害可观测性；部分是有意降级（应至少 debug 日志 + 收窄异常类型） |
| Q-2 | ~40 个函数 | 圈复杂度 >10（门禁阈值 20 偏松）：`check_docs_validate`/`build_document_entry`(20)、`check_deploy_integrity`(19)、`check_protocol_script_references`/`docs_validate`(17)、`deploy_instruction_files`/`check_event_log_schema`(16)… | LOW-MEDIUM | 集中在 CLI 命令与 doctor/framework-review checker；可读性与可测性下降 |
| Q-3 | hook/base、docs/loader、kg/_dispatch、doc_review/template_registry | 4 处裸 `global` 模块级可变缓存，**仅** `adapter/platform/registry.py:22` 用了 `threading.Lock` | MEDIUM(测试隔离)/LOW(线程) | 当前单线程 CLI 安全，但测试间缓存不清除→污染；未来并行（pytest-xdist/并发加载）会触发 TOCTOU |

无裸 `except:`、无可变默认参数、无 `eval/exec`——基础卫生良好。

### 1.6 死代码与冗余（详见 §6 清单）

最高价值：两套 frontmatter 解析器并行（`utils/frontmatter.py` vs `kg/ingest/frontmatter.py`，叠加 `yaml_parser` 包装共三层）；`--no-deploy` 死垫片（注释明写 v0.3 移除，现 0.8.0）；5 个零引用导出。交叉引用 framework-audit R-006「`SparqlRegistry.has()` 恒返回 True」属纯死代码。

### 1.7 测试现状

总体健康：1860 用例 collected 无 collection error，skip/xfail 全部带合法条件原因，无 `assert True`/空测试体/注释断言。缺口：

| ID | 位置 | 问题 | 严重度 |
|----|------|------|--------|
| TE-1 | `doc_review/typed_checks.py`（403 行） | 零直接测试 import（仅经 `DocChecker` 继承链间接覆盖），分支几乎无单测 | HIGH |
| TE-2 | `framework_review/checks/b2.py`/`b8.py`（及 b4 部分） | 关键质量门禁逻辑无直接测试 | HIGH |
| TE-3 | `tests/mcp/test_lifecycle_debug.py:44,68` | mock 私有属性 `lifecycle._registry.get_server`（绕过公开接口，已挂 `type:ignore[method-assign]`） | MEDIUM |
| TE-4 | `tests/utils/test_docker_util_lazy.py:13,21,29` | 3 个仅输入不同的近似重复测试应 parametrize | MEDIUM |
| TE-5 | `tests/cli/test_doctor_*.py` | `_minimal_project`/`_scaffold` 在 4 文件各自重复定义，未提 fixture | LOW |
| TE-6 | 整体 | 估计覆盖率 55-60%（排除 `_generated`） | — |

---

## 2. 目标架构

依赖方向与分层不变（已正确），目标是**让真实依赖图与声明图重合**——消除全部 27 处反向边、把放错层的模块归位、把 deploy 算法收回 runtime。

### 2.1 与现状的主要差异（模块迁移）

```text
src/cataforge/
  interface/cli/
    ui.py                 # 保留渲染实现；ChoiceOption/DiagPattern/pattern-match 下沉（见下）
    + 实现 core.console.Console 端口
  application/
    feedback/             # ← 从 core/feedback/ 整包上移（消除 L-2）
      collectors.py         #   合法向下/同层依赖 application→runtime/domain
      assemblers.py
      renderers.py
    services/  context/    # 不变
  runtime/
    deploy/
      deployer.py           # 瘦身为 pipeline 编排（消除 C-1）
      steps/                # ← deploy 算法从 adapter/_deploy_mixins/ 迁回（消除 C-2/L-4）
        agents.py  instructions.py  skills.py  commands_rules.py  mcp.py
      template_render.py    # ← core/template.py 的 render_runtime_content 上移（消除 L-6）
    mcp/  agent/  skill/  hook/  plugin/   # 不变（lifecycle 拆分见下）
    mcp/lifecycle.py        # 拆出 health_probe.py + state_store.py
  domain/
    kg/
      facade.py             # 扩充：暴露 checker 所需 dispatch/sparql 能力（消除 L-8）
    docs/                   # 不变
  adapter/
    platform/
      adapter.py            # 纯 config/capability carrier：PlatformProfile 类型化（T-1）
      profile_schema.py     # ← 新增 PlatformProfile pydantic 模型（加载期校验）
      claude_code.py …      # 各实现保留平台特定 override（strategy hooks）
      fileops.py            # ← helpers.py 的文件操作部分迁此或 utils（S-2）
      hooks_config.py mcp_config.py  # ← helpers.py 拆分（S-2）
    integrations/penpot/
      __init__.py           # 瘦身为 re-export（S-1）
      commands.py config.py doctor.py patterns.py  # ← 从 __init__ 拆出 + PENPOT_PATTERNS 归位（L-3）
  core/
    console.py            # ← 新增 Console Protocol 端口 + ChoiceOption/DiagPattern 数据类（消除 L-1/L-3/L-5 的 UI 反向边）
    scaffold.py scaffold_backup.py   # 备份/恢复拆出（S-4）
    types.py config.py paths.py events.py …   # 不变
    （删除 core/feedback/、core/template.py 的 adapter 部分）
  utils/
    process.py            # ← pid_alive 等进程原语下沉（消除 L-7）
    console_noop.py?      # 可选：无 CLI 环境的默认 Console 实现
    frontmatter.py        # 统一 frontmatter 解析（消除 2a 三层分叉）
    common.py             # 删除 ui 包装函数（消除 L-1），仅留纯工具
```

### 2.2 三条结构性主线

1. **UI 反向边归零（L-1/L-3/L-5）**：在 `core/console.py` 定义 `Console` Protocol（`section/info/ok/warn/fail/prompt_choice`）+ 纯数据类 `ChoiceOption`/`DiagPattern` + `pattern_matches()` 纯函数。`interface.cli.ui` 实现该 Protocol。下层（utils/adapter/application）不再 import interface，改为**接收注入的 `Console`** 或**返回结构化数据由 interface 渲染**。`PENPOT_PATTERNS` 归 `adapter/integrations/penpot/patterns.py`。

2. **deploy 算法收回 runtime（C-1/C-2/L-4/L-6）**：把 `adapter/platform/_deploy_mixins/*` 迁为 `runtime/deploy/steps/*`，由 deployer 编排，`adapter` 降为**纯 config/capability carrier + 平台特定 strategy hook**。`DeployManifest`/`translate_agent_md`/`render_runtime_content` 与调用方同层（runtime），反向边消失。`Deployer._deploy()` 拆成显式 pipeline step 列表（OCP）。

3. **类型契约显式化（T-1/T-2/T-3/T-4）**：`PlatformProfile`/`HookEntry` 用 pydantic 模型（加载期校验）替换裸 dict；两个 checker mixin 引入 `@abstractmethod`/Protocol 声明契约；统一 `file_cache` 类型。逐包推进 mypy strict。

---

## 3. 重构方案（分组）

每组：目标 / 具体改动（含破坏性）/ 涉及文件 / 预期收益 / 风险。破坏性以 ⚠️ 标注。

### G1 — UI 反向边治理（消除 L-1/L-3/L-5，HIGH）

- **目标**：utils/adapter/application 不再依赖 interface。
- **改动**：
  1. 新增 `core/console.py`：`Console` Protocol + `ChoiceOption`/`DiagPattern` dataclass + `pattern_matches()`。
  2. `interface/cli/ui.py` 显式声明实现 `core.console.Console`；`ChoiceOption`/`DiagPattern` 改为从 core re-export（保对外名不变）。
  3. ⚠️ 删除 `utils/common.py` 的 `section/info/ok/warn/fail` 包装；`docker_util.py`/`penpot` 等调用方改为接收注入 `Console`（构造参数，默认 no-op 实现）。
  4. `penpot` 交互提示改为接收注入 `Console`；`PENPOT_PATTERNS` 移到 `adapter/integrations/penpot/patterns.py`，`interface.cli.diagnostics` 改为从 adapter re-export 或仅保留 doctor/upgrade 模式。
  5. `application/services/bootstrap.py` 的 `classify_tallies` 下沉到 `core`（纯 Counter 聚合）。
- **涉及**：`core/console.py`(新)、`interface/cli/ui.py`、`utils/common.py`、`utils/docker_util.py`、`adapter/integrations/penpot/*`、`interface/cli/diagnostics.py`、`application/services/bootstrap.py`、`core/`（新增 tallies）。
- **收益**：utils/adapter 可在无 CLI 环境独立运行与单测；扇入异常（ui=28）消除；`check_layer_dependencies` 可收紧（见 §7）。
- **风险**：中。`Console` 注入需穿透若干调用栈。兼容基线允许内部模块自由重构，故无需为下游保 re-export shim，直接更新所有内部调用点即可。

### G2 — deploy 算法收回 runtime（消除 C-1/C-2/L-4/L-6，HIGH）

- **目标**：deploy 算法与其依赖（DeployManifest/translator/template）同层；adapter 纯配置化。
- **改动**：
  1. ⚠️ `adapter/platform/_deploy_mixins/{agents,instructions,skills,commands_rules,mcp}.py` → `runtime/deploy/steps/`。`PlatformAdapter` 不再多重继承 deploy mixin，改为被 step 函数**消费**（`deploy_agents(adapter, src, root, ...)`）。
  2. 平台特定差异（如 OpenCode 的 `target_rel`、各端 formatter）保留为 adapter 上的小 strategy 方法/属性，由 step 读取。
  3. ⚠️ `core/template.py` 的 `render_runtime_content(adapter)` → `runtime/deploy/template_render.py`；core 仅保留与 adapter 无关的纯 token 替换（若有）。
  4. `Deployer._deploy()` 拆为显式 `STEPS: list[DeployStep]` pipeline，每个 step 一个小函数/类，`_deploy` 仅遍历+收集 actions（消除 C-1，OCP）。
- **涉及**：`adapter/platform/adapter.py`、4 个平台实现、`adapter/platform/_deploy_mixins/*`（迁移）、`runtime/deploy/deployer.py`、`core/template.py`。
- **收益**：adapter→runtime 反向边（L-4）与 core→adapter（L-6）归零；deploy 各 step 可独立单测（补 TE 缺口）；新增资产类型只加 step。
- **风险**：⚠️ **高**。这是最大破坏性改动，触及部署核心路径。兼容基线允许 `DeployManifest` 磁盘格式有意变更，故不再要求字节兼容；但**功能正确性是硬边界**：deploy 产物布局须仍被各 IDE 识别、幂等/prune 语义须仍成立、`cataforge deploy` 重跑结果须稳定。回滚点：每个 step 一个 PR，先 thin-delegate 后内联（便于分次 squash-merge），无需保留旧 mixin 长期过渡版本。

### G3 — 模块归位与拆分（S-1/S-2/S-3/S-4/L-7，MEDIUM）

- **改动**：
  1. ⚠️ `penpot/__init__.py` → 拆 `commands.py`/`config.py`/`doctor.py`/`patterns.py`，`__init__` 仅 re-export（S-1/L-3）。
  2. `adapter/platform/helpers.py` → 拆 `fileops.py`（迁 utils 或 adapter）/`hooks_config.py`/`mcp_config.py`（S-2）。
  3. `runtime/mcp/lifecycle.py` → 拆 `health_probe.py`（3 协议）/`state_store.py`（JSON 持久化）；`pid_alive`+进程原语 → `utils/process.py`（S-3/L-7，移除 penpot 的 `allow-layer-dep`）。
  4. `core/scaffold.py` → 备份/恢复拆 `core/scaffold_backup.py`（S-4）。
- **收益**：god module 解体；`pid_alive` 跨层借用合法化（下沉 utils）。
- **风险**：中。纯搬迁 + re-export，破坏性低；逐文件可验证。

### G4 — `core/feedback` 上移 application（消除 L-2，HIGH）

- **改动**：⚠️ `core/feedback/` 整包 → `application/feedback/`。delete `core/feedback/collectors.py` 的延迟 import shim，改为 application 层正常向下/同层 import（application→runtime/domain 合法）。更新所有 `from cataforge.core.feedback import …`（主要在 `interface/cli/feedback_cmd.py`）。
- **收益**：core 层 import application/runtime 的两条最严重穿透边消失；`feedback` 可正常类型检查与测试。
- **风险**：中。import 路径变更需全局替换；feedback CLI 行为不变（仅模块位置变）。

### G5 — 类型契约显式化（T-1~T-4/T-7，HIGH/MEDIUM）

- **改动**：
  1. ⚠️ 新增 `adapter/platform/profile_schema.py`：`PlatformProfile` **pydantic BaseModel**（加载期校验）；`load_profile()` 返回校验后的模型实例；`PlatformAdapter.__init__` 与属性返回类型替换裸 `dict[str,Any]`（T-1）。畸形 profile.yaml 在加载期即报清晰错误（前移失败时机）。
  2. ⚠️ `runtime/hook/bridge.py`：`HookEntry`/`HooksSpec` **pydantic 模型**（T-2），与既有 `core/schema/mcp_spec.py` 用法一致。
  3. `TypedDocChecksMixin`/`_CrossDocChecksMixin`：加 `@property @abstractmethod` 声明 `volume_type/content/lines` 等，或改 Protocol + `DocChecker` 标注实现（T-3，消 122 个 attr-defined）。
  4. 统一 `file_cache: dict[str,list[str]] | None`（T-4）；`get_config_manager()` 补返回注解（T-7）。
  5. 清理 `kg/query.py` 6 处失效 `type:ignore`（T-5）；修 `doctor_cmd.py:159` 退出码类型（T-6，拆 check/report 两类或显式标注 `_DOCTOR_SECTIONS`）。
- **收益**：profile/hooks/checker 契约静态可查 + 加载期强校验；mypy 错误显著下降；为逐包 strict 铺路。
- **风险**：中。pydantic 校验改变对畸形 profile.yaml 的失败时机（运行时→加载期）与错误信息——**必须新增容错回归测试**：既有合法 profile 全部通过校验、畸形 profile 给出可定位的字段级错误，避免把"宽松 .get() 容错"回退成"加载即崩"。⚠️ 标注项为对外可观察行为变化（虽兼容基线允许，但需测试托底）。

### G6 — 代码质量收尾（Q-1/Q-2/Q-3，MEDIUM/LOW）

- **改动**：
  1. Q-3：4 处裸 `global` 缓存改 `functools.lru_cache`/`threading.Lock`，或加 `conftest.py` autouse fixture 统一 `clear_cache()`（优先后者解决测试隔离，前者解决并发）。
  2. Q-1：静默 `except Exception` 收窄异常类型 + 加 `logger.debug`；保留有意降级但留证据。
  3. Q-2：高复杂度 CLI/checker 函数抽取子函数（结合 G2 的 pipeline 拆分顺带降复杂度）；评估把 ruff `max-complexity` 从 20 收紧到 15。
- **风险**：低。

---

## 4. 测试改造计划

原则：结构性破坏（G2/G4）前先建立**等价或更强**的验证网；新结构按 step/模块补单测。

### 4.1 新增（补缺口 + 为重构托底）

| 优先级 | 目标 | 理由 |
|--------|------|------|
| P0 | `tests/.../test_typed_checks.py` 覆盖 `TypedDocChecksMixin` 各分支（TE-1） | 403 行零直接覆盖，G5-3 重构 mixin 前必须有网 |
| P0 | `tests/.../test_framework_review_b2.py` / `b8.py`（TE-2） | 关键质量门禁逻辑无测，改动风险高 |
| P0 | `tests/deploy/steps/test_*.py`——每个 deploy step 单测（G2 前置） | G2 是最高破坏性改动；step 级单测是其回滚保险 |
| P1 | `tests/core/test_console.py`——`Console` Protocol + `pattern_matches`（G1） | 新端口需契约测试 |
| P1 | `runtime/mcp/lifecycle._probe_http/_build_env` 直接单测 | 当前仅集成覆盖（TE 中等缺口） |
| P1 | `application/feedback/` 迁移后的独立单测（G4 后，不再需 CLI 栈） | 验证脱钩成功 |

### 4.2 改写

| 目标 | 改法 |
|------|------|
| `tests/mcp/test_lifecycle_debug.py:44,68`（TE-3） | mock 私有 `_registry` 改为构造注入或 `monkeypatch.setattr` 公开接口 |
| `tests/utils/test_docker_util_lazy.py:13,21,29`（TE-4） | 合并为单个 `@pytest.mark.parametrize` |
| `tests/cli/test_doctor_*.py`（TE-5） | `_minimal_project` 提为 `tests/cli/conftest.py` 工厂 fixture |
| `tests/cli/conftest.py` | `populate_required_source_assets` 由直接 import 改 fixture 注入 |

### 4.3 废弃

- 随死代码删除（§6）连带删除其结构性测试：`test_diagnostics.py:62`（断言 `UPGRADE_PATTERNS` 长度）、`--no-deploy` 的 deprecation 警告测试（若有）。
- G2 完成后，`tests/platform/test_adapter.py` 中针对 mixin 多继承的测试改为针对 `runtime/deploy/steps` 的 step 测试。

### 4.4 覆盖率目标

| 模块组 | 现状估计 | 目标 |
|--------|---------|------|
| `doc_review/`（含 typed_checks） | ~55% | 70% |
| `framework_review/`（补 b2/b8） | ~50% | 75% |
| `runtime/deploy/steps/`（G2 后） | — | 65% |
| `adapter/platform/`（纯配置后更易测） | ~65% | 70% |
| `interface/cli/helpers.py`+`guards.py` | ~20% | 60% |
| **整体（排除 `_generated`）** | **55-60%** | **70%** |

引入 `pytest-cov` 门禁（`--cov-fail-under`）应**在覆盖率达标后**开启，先以报告模式运行若干 PR 建立基线。

---

## 5. 执行计划

按依赖与风险分阶段。每阶段验证：`uv run --extra dev python scripts/checks/run_local.py`（ruff + 全守卫 + lock 新鲜度）+ `uv run --extra dev pytest`（必要时 `-m 'not slow'`）+ 受影响包 `mypy`。回滚点 = 每个可独立 squash-merge 的 PR。

| 阶段 | 内容 | 破坏性/风险 | 验证 | 回滚点 |
|------|------|------------|------|--------|
| **0. 安全网** | §4.1 P0 测试（typed_checks/b2/b8/deploy steps 现状行为快照）+ §6 高置信死代码删除 | 低（删死代码⚠️低） | pytest + run_local | 独立 PR，每类死代码一 PR |
| **1. 类型契约** | G5：profile/hooks 改 **pydantic**（加载期校验）、mixin 契约、清失效 ignore、修退出码类型、补返回注解 | 低（mixin/注解纯静态）；⚠️ 低-中（pydantic 改 profile.yaml 失败时机） | mypy 受影响包错误数下降 + pytest + **profile 容错回归测试** | 按 T-1/T-2/T-3… 拆 PR；pydantic 单独一 PR |
| **2. 模块下沉（低破坏）** | G3：`pid_alive`→utils/process、helpers 拆分、lifecycle 拆分、scaffold_backup 拆分（直接更新调用点，无需 re-export shim） | 低（纯搬迁） | run_local（含 layer 守卫）+ pytest | 每文件一 PR |
| **3. UI 反向边（中破坏）** | G1：`core/console` 端口 + 注入；删 utils.common ui 包装；PENPOT_PATTERNS 归位；classify_tallies 下沉 | ⚠️ 中 | layer 守卫 + pytest + 手测 `penpot`/`doctor` 交互 | G1 可拆 console 端口 / 各调用方注入两步 |
| **4. feedback 上移（中破坏）** | G4：`core/feedback`→`application/feedback`，删 shim，改 import | ⚠️ 中 | layer 守卫 + `cataforge feedback bug/suggest` 端到端 | 单 PR（含全局 import 替换） |
| **5. deploy 收回 runtime（高破坏，全量迁移）** | G2：mixin→`runtime/deploy/steps`、adapter 纯配置化、template_render 上移、`_deploy()` pipeline 化 | ⚠️⚠️ 高 | 全量 pytest + `tests/e2e/test_deploy_links_and_doctor.py`（真实 wheel→deploy→doctor）+ 四端 `deploy --dry-run` 结构对比（manifest 格式可有意变更，验功能正确而非字节一致） | step 先 thin-delegate 旧 mixin，分 PR 逐 step 内联 |
| **6. 守卫收紧 + 收尾** | §7 守卫增强（函数内/TYPE_CHECKING 向上 import 纳入 ledger）、G6 质量收尾、覆盖率门禁基线 | 低 | run_local + CI | 守卫先 warn 后 fail |

阶段 0/1/2 可并行推进（互不依赖）；3→4→5 有弱顺序（G1 的 console 注入便于 G2 的 step 测试，G4 先于 G5 的 feedback strict）。**阶段 5 是唯一高风险节点**，对应 COMMON-RULES 的 `pre_dev` 人工检查点，建议单独评审 go/no-go。

---

## 6. 死代码清理清单

均经 `grep src/ tests/` 引用关系核验。

### 高置信可删（已亲自核验零引用）

| # | 位置 | 判定依据 |
|---|------|---------|
| D-1 | `core/types.py:35` `DispatchRequest` dataclass | 全库仅定义处一行命中，无 import/无测试 |
| D-2 | `interface/cli/stubs.py:24` `exit_not_implemented()` | 仅定义 + `__all__`，无调用方（CLI 改 raise `CataforgeError`）；保留 `STUB_EXIT_CODE`（`test_cli_smoke.py:375` 仍用） |
| D-3 | `utils/common.py:43` `section()` 包装 | 无调用方（`ui.section()` 是直接调 ui 对象，非经此包装）；随 G1 一并清理 |
| D-4 | `utils/yaml_parser.py:20` `dump_yaml()` | 全库零引用 |
| D-5 | `interface/cli/diagnostics.py:113-123` `UPGRADE_PATTERNS`/`UPGRADE_LOCAL_MODS` | src 中无 import，仅 `test_diagnostics.py:62` 断言长度；`upgrade_cmd.py` 未接入 |
| D-6 | `interface/cli/setup_cmd.py:62-136,212` + `bootstrap_cmd.py:205-208` `--no-deploy` | 注释明写 "will be removed in v0.3"，现 0.8.0；已是 deprecated no-op，调用方显式传 `no_deploy=False` 仅为避免警告 |

### 高置信冗余合并

| # | 位置 | 处理 |
|---|------|------|
| D-7 | `utils/frontmatter.split_yaml_frontmatter` vs `kg/ingest/frontmatter.parse_frontmatter`（+ `yaml_parser.parse_yaml_frontmatter` 三层叠加） | 统一为单一解析器，错误语义（静默 `{}` vs `__parse_error__`+warning）由参数控制；`doc_consistency/_parse.py:9-11` 同时引两者，是分叉见证 |
| D-8 | `claude_code.py:61-71` vs `opencode.py:53-63` `deploy_agents` 近似克隆 | OpenCode 的 `target_rel` 改从 profile 读，可删 override（随 G2 一并处理） |

### 需进一步确认（勿擅删）

| # | 位置 | 待确认 |
|---|------|--------|
| D-9 | `domain/kg/nl_query.py` 全部公共函数（`translate/query/answer`） | 公共 API 顾虑已消除（兼容基线：内部模块非契约）。剩余唯一问题：是否为**待接线的功能**（NL→SPARQL，目前无 CLI 入口）？若非计划接线即可删（连带 `test_nl_query.py`）——这是产品取舍，非兼容问题 |
| D-10 | framework-audit **R-006** `SparqlRegistry.has()` 恒返回 True | 渲染层早退守卫纯死代码（交叉引用，已在前序审计登记，应一并修） |
| D-11 | `.cataforge/framework.json` 11 条 `deprecate_after:"0.2.0"` migration_checks | 运行时已自动跳过（0.8.0≫0.2.0），下次 scaffold 升级时全量覆盖清除（`upgrade.source` 声明安全） |
| D-12 | `domain/docs/migrate_nav.py`、`migrate_review_frontmatter.py`、`event accept-legacy` | 一次性迁移工具，对老项目仍有用途；评估归档而非删除。**注**：`protocol_refs.py` 的 NAV-INDEX 废弃引用检测是**在用守卫**，保留 |

### 硬编码（技术债，非严格违规）

`doc_review/constants.py:5` `DOC_SPLIT_THRESHOLD_LINES=300` 与 `skill/runner.py:19` `_DEFAULT_TIMEOUT_SECS=300` 是 `framework.json` 常量的 Python-side fallback（有从 config 优先读取的机制），CLAUDE.md 约束针对 SKILL.md/AGENT.md/模板，二者不严格违规，但数字重复——可改为从单一来源派生 fallback。

---

## 7. 工具与门禁建议

| 工具 | 用途 | 接入建议 |
|------|------|---------|
| **强化 `check_layer_dependencies.py`** | 当前盲区：函数内 / `TYPE_CHECKING` 向上 import 被豁免，藏了 27 处反向边 | 新增"向上 import ledger"模式：函数内/TYPE_CHECKING 的向上 import 不再静默豁免，而是与 allowlist 对账，新增即 warn→后续 fail。把豁免从"无限额"变"有账本" |
| **import-linter** | 声明式分层契约（`forbidden`/`layers` contract）作为 AST 守卫的补充第二意见 | 加 `[tool.importlinter]`，contract 编码 `interface→…→utils` 单向；CI 跑。注意它只看静态图，需与强化后的 AST 守卫配合 |
| **mypy 逐包 strict** | 已有 opt-in 机制（`application.services.*`） | 按 §3 G5 清理后，依次将 `core`→`utils`→`adapter.platform`→`runtime.deploy` 加入 `[[tool.mypy.overrides]] strict` |
| **vulture**（环境缺失） | 死代码持续检测，巩固 §6 成果 | 加 dev 依赖 + `vulture src/ --min-confidence 80`，先报告后门禁；维护 whitelist |
| **pytest-cov 门禁** | 防覆盖率回流 | 先报告模式建基线，达 §4.4 后开 `--cov-fail-under=70`（排除 `_generated`） |
| **ruff 收紧** | C901 阈值 20 偏松（40 函数 >10） | 结合 G2/G6 降复杂度后，`max-complexity` 20→15 |
| **pre-commit** | 已配置 | 上述新守卫一并挂钩；`run_local.py` 的 `CHECKS` 同步登记 |

---

## 8. 遗留与待澄清

### 暂不建议改动

- **`domain/kg/_generated/`**（4920 行）：LinkML codegen 产物，已 ruff/pyright 豁免，mypy 80 错全在此——不手改，由 `scripts/codegen_kg_schema.py` 重生成。
- **三份相同的 `_clear_adapter_cache` autouse fixture**（`tests/{agent,hook,platform}/conftest.py`）：合并收益 < 跨目录 autouse 的清晰度损失，保留。
- **framework_review 独立 `Finding/Report`（FAIL/WARN/INFO）vs 全局 `Issue/CheckReport`（四级 severity）**：语义轴不同，是有意分叉，不强行统一（但应在文档备注以防误用）。

### 已决策（2026-06）

原"待澄清硬边界"已全部拍板，明细与涟漪见 §0.1。摘要：

1. **兼容基线 = 全部可自由重构**：CLI 命令面、deploy 产物布局、`DeployManifest` 磁盘格式、内部 Python 模块均视为非契约（假设无 in-the-wild 静默升级）。⇒ 模块迁移免 re-export shim；manifest 格式可有意变更。
2. **profile/hooks 建模 = pydantic**：加载期强校验，畸形配置失败前移；须补容错回归测试（G5）。
3. **最低 Python = ≥3.11**：放弃 3.10。⇒ 可用 `tomllib`（替换 codex TOML 读取的手写处理）、`typing.Self`；执行杂项：`pyproject.toml` 的 `requires-python`/classifiers、`ruff target-version`/`mypy python_version`/`pyright pythonVersion`、CI matrix 同步去 3.10。
4. **阶段 5 = 全量迁移**：deploy 算法物理收回 runtime，adapter 纯配置化；仍设为 `pre_dev` 检查点，安全网就绪后单独 go/no-go。

### 剩余待确认（产品级，非兼容问题）

- **D-9 `domain/kg/nl_query.py`**：NL→SPARQL 是否为待接线功能？若非计划接线即可整模块删除——这是产品取舍，需产品方一句确认。
- **framework-audit R-006（`SparqlRegistry.has()` 恒 True）**：本方案在 §6 D-10 交叉登记为应一并修的死守卫，具体修法归前序 audit 的 remediation 轨道，避免两轮重复。

---

## 附：证据来源

本方案由 4 路并行审计 + 直接核查产出，全部结论可经 `grep`/`mypy`/`ruff`/AST 复现：

- 分层耦合：AST 全量 import 图分析 → 27 反向边、283 函数内延迟 import、扇入/扇出 Top
- 类型契约：`mypy src/cataforge`（458 错）+ `dict[str,Any]` 计数（158）+ Protocol/ABC 清点
- 死代码重复：`grep` 引用关系核验（D-1~D-6 已逐条确证零引用）
- 测试现状：`pytest --collect-only`（1860 用例）+ fixture/mock/parametrize 密度 + 镜像缺口
