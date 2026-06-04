# 重构 PR 拆分清单（可勾选）

> 配套 [`refactor-plan.md`](./refactor-plan.md) §5 执行计划的 PR 级展开。每条对应一个**可独立 squash-merge、可验证、可回滚**的 PR。
> 勾选规则：PR 合并后把 `- [ ]` 改 `- [x]`。标题即未来 PR 标题，已按 CLAUDE.md §Git 工作流的 conventional-commits 写好（过 `pr-title.yml`）。
> 标注语义：**依赖** = 必须先合并的 PR；**风险** 低 / 中 / ⚠️高；**验证** = 合并前最小验证命令。不写工时（见 COMMON-RULES §禁止估算任务用时），用风险/复杂度维度。
> 关联 finding ID 见主方案 §1（S/L/C/T/Q/TE）、§6（D）。

---

## 阶段 0 · 基础设施 + 安全网 + 死代码

低风险、互不依赖、可全部并行；为后续阶段铺底。

- [ ] **PR-01** `chore(build): raise python floor to 3.11`
  - 动作：`pyproject.toml` `requires-python` `>=3.10`→`>=3.11`、删 3.10 classifier；`ruff target-version`/`mypy python_version`/`pyright pythonVersion` 同步；CI matrix 去 3.10（决策 3）
  - 依赖：无 · 风险：低 · 验证：`run_local` + 全 CI matrix
- [ ] **PR-02** `test(skill): snapshot doc_review typed_checks branches`
  - 动作：为 `TypedDocChecksMixin` 各检查分支补现状行为单测（TE-1），作为 PR-08 重构前的安全网
  - 依赖：无 · 风险：低 · 验证：`pytest tests/skill`
- [ ] **PR-03** `test(skill): cover framework-review b2/b8 checks`
  - 动作：补 `framework_review/checks/b2.py`/`b8.py` 直接单测（TE-2）
  - 依赖：无 · 风险：低 · 验证：`pytest tests/skill`
- [ ] **PR-04** `chore(core): drop unreferenced DispatchRequest and dump_yaml`
  - 动作：删 `core/types.py` `DispatchRequest`、`utils/yaml_parser.py` `dump_yaml`（D-1/D-4，零引用）
  - 依赖：无 · 风险：低 · 验证：`run_local`（ruff F401）+ `pytest`
- [ ] **PR-05** `chore(cli): remove exit_not_implemented stub`
  - 动作：删 `interface/cli/stubs.py` `exit_not_implemented`，保留 `STUB_EXIT_CODE`（D-2）
  - 依赖：无 · 风险：低 · 验证：`pytest tests/cli`
- [ ] **PR-06** `chore(cli): drop unused upgrade diagnostics patterns`
  - 动作：删 `diagnostics.py` `UPGRADE_PATTERNS`/`UPGRADE_LOCAL_MODS` + `test_diagnostics.py:62` 结构断言（D-5）
  - 依赖：无 · 风险：低 · 验证：`pytest tests/cli`
- [ ] **PR-07** `chore(cli): remove deprecated --no-deploy flag`
  - 动作：删 `setup_cmd.py` `--no-deploy` 声明/警告分支 + `bootstrap_cmd.py` 传参（D-6）
  - 依赖：无 · 风险：低 · 验证：`pytest tests/cli` + 手测 `setup`/`bootstrap`

## 阶段 1 · 类型契约（G5）

低-中风险；可与阶段 0/2 并行。

- [ ] **PR-08** `refactor(skill): declare typed-check mixin contracts`
  - 动作：给 `TypedDocChecksMixin`/`_CrossDocChecksMixin` 加 `@property @abstractmethod` 或改 Protocol（T-3，消 122 个 attr-defined）
  - 依赖：PR-02（mixin 测试网）· 风险：低（纯静态）· 验证：`mypy src/cataforge/runtime/skill/builtins/doc_review src/cataforge/runtime/skill/builtins/doc_consistency` + `pytest`
- [ ] **PR-09** `fix(cli): annotate get_config_manager and doctor exit-code types`
  - 动作：补 `get_config_manager()` 返回注解（T-7）；修 `doctor_cmd.py:159` 退出码 `int|None`（T-6，拆 check/report 或标注 `_DOCTOR_SECTIONS`）
  - 依赖：无 · 风险：低 · 验证：`mypy src/cataforge/interface/cli` + `pytest tests/cli`
- [ ] **PR-10** `fix(cli): drop stale type-ignore in kg query`
  - 动作：清 `kg/query.py` 6 处失效 `type:ignore` 并修其掩盖的 `attr-defined`（T-5）
  - 依赖：无 · 风险：低 · 验证：`mypy --warn-unused-ignores src/cataforge/interface/cli/kg`
- [ ] **PR-11** `fix(docs): unify file_cache element type`
  - 动作：统一 `file_cache: dict[str, list[str]] | None`（ports/backends/loader，T-4）
  - 依赖：无 · 风险：低 · 验证：`mypy src/cataforge/application/context src/cataforge/domain/docs`
- [ ] **PR-12** `feat(platform): pydantic PlatformProfile model` ⚠️
  - 动作：新增 `adapter/platform/profile_schema.py`（pydantic），`load_profile()` 返回校验模型，adapter 属性去裸 dict（T-1）；**新增畸形 profile 容错回归测试**
  - 依赖：无 · 风险：⚠️低-中（profile.yaml 失败时机前移）· 验证：`pytest tests/platform`（含畸形用例）+ `mypy`
- [ ] **PR-13** `feat(hook): pydantic HookEntry and HooksSpec models`
  - 动作：`runtime/hook/bridge.py` 用 pydantic 模型替换 `dict[str,Any]`（T-2）
  - 依赖：无 · 风险：低-中 · 验证：`pytest tests/hook` + `mypy`

## 阶段 2 · 模块下沉与拆分（G3 + D-7）

低风险纯搬迁；可与阶段 0/1 并行。直接更新调用点，无需 re-export shim（兼容基线决策）。

- [ ] **PR-14** `refactor(utils): add process module for pid_alive`
  - 动作：`pid_alive`+进程原语 `runtime/mcp/lifecycle.py`→`utils/process.py`；删 penpot `allow-layer-dep`（S-3/L-7）
  - 依赖：无 · 风险：低 · 验证：`run_local`（layer 守卫）+ `pytest tests/mcp tests/integrations`
- [ ] **PR-15** `refactor(platform): split helpers into fileops/hooks_config/mcp_config`
  - 动作：`adapter/platform/helpers.py`（594 行）拆三模块（S-2）
  - 依赖：无 · 风险：低 · 验证：`run_local` + `pytest tests/platform`
- [ ] **PR-16** `refactor(mcp): split lifecycle into health_probe and state_store`
  - 动作：`lifecycle.py` 拆健康探测（3 协议）+ JSON 状态持久化（S-3）
  - 依赖：PR-14 · 风险：低 · 验证：`pytest tests/mcp`
- [ ] **PR-17** `refactor(scaffold): extract scaffold_backup module`
  - 动作：`core/scaffold.py` 备份/恢复（8 函数）拆 `core/scaffold_backup.py`（S-4）
  - 依赖：无 · 风险：低 · 验证：`pytest tests/core`
- [ ] **PR-18** `refactor(utils): unify frontmatter parsers`
  - 动作：合并 `utils/frontmatter` 与 `kg/ingest/frontmatter`（+ `yaml_parser` 包装）为单一解析器，错误语义由参数控制（D-7）
  - 依赖：无 · 风险：中（错误语义合并需双侧测试）· 验证：`pytest tests/kg tests/skill`（覆盖 doc_consistency + kg ingest 两条路径）

## 阶段 3 · UI 反向边治理（G1）

中风险；建议在阶段 2 之后。消除 L-1/L-3/L-5 的 UI 反向边。

- [ ] **PR-19** `feat(core): add Console port and ui data types`
  - 动作：`core/console.py`：`Console` Protocol + `ChoiceOption`/`DiagPattern` dataclass + `pattern_matches()`（G1.1）
  - 依赖：无 · 风险：低 · 验证：`pytest tests/core/test_console`
- [ ] **PR-20** `refactor(cli): implement core Console in ui`
  - 动作：`interface/cli/ui.py` 声明实现 `core.console.Console`，数据类从 core re-export（G1.2）
  - 依赖：PR-19 · 风险：中 · 验证：`pytest tests/cli/test_ui`
- [ ] **PR-21** `refactor(utils): drop ui wrappers from common` ⚠️
  - 动作：删 `utils/common.py` `section/info/ok/warn/fail`（含 D-3）；`docker_util` 等调用方改注入 `Console`（G1.3/L-1）
  - 依赖：PR-19, PR-20 · 风险：⚠️中 · 验证：`run_local`（layer 守卫）+ `pytest` + 手测 `docker_util` 输出
- [ ] **PR-22** `refactor(penpot): inject Console and relocate patterns`
  - 动作：penpot 交互改注入 `Console`；`PENPOT_PATTERNS`→`penpot/patterns.py`（G1.4/L-3）
  - 依赖：PR-19, PR-20 · 风险：中 · 验证：`run_local`（layer 守卫）+ 手测 `penpot`/`doctor` 交互
- [ ] **PR-23** `refactor(core): move classify_tallies down from cli`
  - 动作：`classify_tallies`（纯 Counter 聚合）`interface.cli.helpers`→`core`（G1.5/L-5 前半）
  - 依赖：无 · 风险：低 · 验证：`run_local`（layer 守卫）+ `pytest`

## 阶段 4 · application→interface 解耦 + feedback 上移（G4 + L-5 后半）

中风险。

- [ ] **PR-24** `refactor(cli): expose doctor summary as a service`
  - 动作：把 `doctor_summary.py` 经 Click `CliRunner` 反向驱动 CLI 改为直接调用提取出的 doctor 服务函数，消除 application→interface 执行边（L-5 后半）
  - 依赖：无 · 风险：中 · 验证：`run_local`（layer 守卫）+ `pytest tests/services tests/cli/test_doctor*`
- [ ] **PR-25** `refactor(feedback): relocate core/feedback to application` ⚠️
  - 动作：`core/feedback/`→`application/feedback/`，删延迟 import shim，全局改 import（G4/L-2）
  - 依赖：PR-24（doctor 服务化后 feedback 不再间接拉 interface）· 风险：⚠️中 · 验证：`run_local`（layer 守卫）+ `cataforge feedback bug/suggest` 端到端 + `pytest tests/core/test_feedback`（迁移后）

## 阶段 5 · deploy 算法收回 runtime（G2，全量迁移）⚠️⚠️

最高破坏性节点，对应 `pre_dev` 检查点，整阶段单独 go/no-go。每个 step 先 thin-delegate 旧 mixin 再内联，分 PR 推进。

- [ ] **PR-26** `test(deploy): snapshot deploy-step and manifest behavior`
  - 动作：固化各 deploy step 与 manifest 现状行为快照，作为迁移安全网（G2 前置）
  - 依赖：无 · 风险：低 · 验证：`pytest tests/deploy` + `pytest -m slow tests/e2e/test_deploy_links_and_doctor.py`
- [ ] **PR-27** `refactor(deploy): introduce explicit step pipeline`
  - 动作：`Deployer._deploy()` 拆为 `STEPS` 列表，`_deploy` 仅遍历+收集 actions（G2.4/C-1，暂不迁物理位置）
  - 依赖：PR-26 · 风险：中 · 验证：全量 `pytest` + e2e
- [ ] **PR-28** `refactor(deploy): migrate agent and instruction steps to runtime` ⚠️
  - 动作：`_deploy_mixins/{agents,instructions}.py`→`runtime/deploy/steps/`，改为消费 adapter（G2.1）
  - 依赖：PR-27, PR-12（typed profile）· 风险：⚠️高 · 验证：全量 `pytest` + e2e + 四端 `deploy --dry-run` 结构对比
- [ ] **PR-29** `refactor(deploy): migrate skill/command/mcp steps to runtime` ⚠️
  - 动作：`_deploy_mixins/{skills,commands_rules,mcp}.py`→`runtime/deploy/steps/`；顺带消 `deploy_agents` 克隆（D-8）
  - 依赖：PR-28 · 风险：⚠️高 · 验证：同 PR-28
- [ ] **PR-30** `refactor(deploy): move template render out of core`
  - 动作：`core/template.py` `render_runtime_content`→`runtime/deploy/template_render.py`（G2.3/L-6）
  - 依赖：PR-28 · 风险：中 · 验证：`run_local`（layer 守卫）+ `pytest` + e2e
- [ ] **PR-31** `refactor(platform): reduce adapter to config carrier` ⚠️
  - 动作：`PlatformAdapter` 去掉 5 个 deploy mixin 多继承，降为纯 config/capability carrier + strategy hook（G2.2）
  - 依赖：PR-28, PR-29, PR-30 · 风险：⚠️高 · 验证：全量 `pytest` + e2e + `run_local`（layer 守卫应显示 adapter→runtime 反向边消失）

## 阶段 6 · 守卫收紧 + 质量收尾（G6 + §7）

低风险；守卫类 PR 需在反向边清零（阶段 3/4/5 完成）后才能从 warn 转 fail。

- [ ] **PR-32** `refactor(core): scope module-level caches for isolation`
  - 动作：5 处裸 `global` 缓存加 `conftest.py` autouse `clear_cache()`（测试隔离）+ `lru_cache`/`Lock`（并发）（Q-3）
  - 依赖：无 · 风险：低 · 验证：`pytest -p xdist -n auto` 烟测
- [ ] **PR-33** `refactor: narrow broad except and add debug logging`
  - 动作：静默 `except Exception` 收窄异常类型 + 补 `logger.debug`，保留有意降级但留证据（Q-1）
  - 依赖：无 · 风险：低 · 验证：`pytest`
- [ ] **PR-34** `ci: enforce upward-import ledger in layer guard`
  - 动作：强化 `check_layer_dependencies.py`——函数内/`TYPE_CHECKING` 向上 import 与 allowlist 对账，新增即 warn→fail（§7）
  - 依赖：阶段 3/4/5 完成（反向边清零）· 风险：低（先 warn）· 验证：`run_local`
- [ ] **PR-35** `ci: add import-linter layered contract`
  - 动作：加 `[tool.importlinter]` 单向分层 contract + CI 跑（§7）
  - 依赖：PR-34 · 风险：低 · 验证：CI `lint-imports`
- [ ] **PR-36** `ci: tighten ruff complexity and add strict mypy packages`
  - 动作：ruff `max-complexity` 20→15（结合 Q-2/G2 降复杂度后）；`core`/`utils`/`adapter.platform`/`runtime.deploy` 逐个加 mypy strict；`pytest-cov` 基线（§7/G6）
  - 依赖：阶段 1/5/PR-33 完成 · 风险：低 · 验证：`run_local` + `mypy`
- [ ] **PR-37** `chore(skill): resolve confirmation-gated dead code`
  - 动作：待产品确认后清理 `nl_query`（D-9）、R-006 死守卫（D-10）、`governance_pydantic`（D-14）、`issue.py:255` `_TODO` 措辞（D-13）
  - 依赖：产品确认（见主方案 §8 剩余待确认）· 风险：低 · 验证：`pytest`

---

## 关键路径与并行批次

- **可立即并行启动**：阶段 0（PR-01~07）、阶段 1（PR-08~13）、阶段 2（PR-14、15、17、18）——互不依赖。
- **阶段内串行**：PR-16←PR-14；PR-20←PR-19、PR-21/22←PR-19+20；PR-25←PR-24。
- **唯一长关键路径**（阶段 5）：PR-26 → PR-27 → PR-28 → PR-29 → PR-31，其中 PR-28 还需 PR-12 先落；PR-30 在 PR-28 后并入。
- **守卫收口压轴**：PR-34/35 必须等阶段 3/4/5 的反向边全部清零，否则守卫转 fail 会立即红。
- **go/no-go 闸**：进入阶段 5 前（PR-26 之后、PR-28 之前）按 `pre_dev` 检查点人工评审；若否决，止步 PR-27（仅 pipeline 化的低破坏增量）。

合计 37 个 PR：⚠️高风险 4（PR-28/29/31 + 整阶段 5 闸）、⚠️中 4（PR-12/21/25 及破坏性标注项）、其余低-中。
