# 重构任务清单（可勾选）

> 配套 [`refactor-plan.md`](./refactor-plan.md) §5 执行计划的任务级展开。每条 `TASK-NN` 是一个**可独立 squash-merge、可验证、可回滚**的工作单元（落地时即一个 PR；此处用 task-id 而非 PR 号，避免与真实 GitHub PR 编号混淆）。
> 勾选规则：任务合并后把 `- [ ]` 改 `- [x]`。标题即未来 PR 标题，已按 CLAUDE.md §Git 工作流的 conventional-commits 写好（过 `pr-title.yml`）。
> 标注语义：**依赖** = 必须先合并的 task；**风险** 低 / 中 / ⚠️高 / ⚠️⚠️极高；**验证** = 合并前最小验证命令。不写工时（见 COMMON-RULES §禁止估算任务用时）。
> 关联 finding ID 见主方案 §1（S/L/C/T/Q/TE）、§6（D）。

---

## 阶段 0 · 基础设施 + 安全网 + 死代码

低风险、互不依赖、可并行。

- [ ] **TASK-01** `chore(build): raise python floor to 3.11`
  - 动作：`requires-python` `>=3.10`→`>=3.11`、删 3.10 classifier；`ruff target-version`/`mypy python_version`/`pyright pythonVersion` 同步；CI matrix 去 3.10（决策 3）
  - 依赖：无 · 风险：低 · 验证：`run_local` + 全 CI matrix
- [ ] **TASK-02** `chore: remove high-confidence dead code`
  - 动作：删 `DispatchRequest`、`dump_yaml`、`exit_not_implemented`、`UPGRADE_PATTERNS`/`UPGRADE_LOCAL_MODS`、`--no-deploy` 垫片 + 连带结构测试（D-1/D-2/D-4/D-5/D-6）
  - 依赖：无 · 风险：低 · 验证：`run_local`（ruff F401）+ `pytest`
- [ ] **TASK-03** `test(skill): add safety-net for typed_checks and framework-review checks`
  - 动作：补 `doc_review/typed_checks` 各分支 + `framework_review/checks/b2`/`b8` 现状行为单测（TE-1/TE-2），作为后续重构的网
  - 依赖：无 · 风险：低 · 验证：`pytest tests/skill`

## 阶段 1 · 类型契约（G5）

可与阶段 0/2 并行。

- [ ] **TASK-04** `refactor(type): mixin contracts, stale ignores, missing annotations`
  - 动作：给 `TypedDocChecksMixin`/`_CrossDocChecksMixin` 加契约声明（T-3，消 122 attr-defined）；清 `kg/query.py` 失效 `type:ignore`（T-5）；补 `get_config_manager()` 注解 + 修 doctor 退出码类型（T-7/T-6）；统一 `file_cache` 类型（T-4）
  - 依赖：TASK-03（mixin 测试网）· 风险：低（纯静态）· 验证：`mypy`（受影响包）+ `pytest`
- [ ] **TASK-05** `feat: pydantic models for platform profile and hooks` ⚠️
  - 动作：新增 `adapter/platform/profile_schema.py` + `runtime/hook` 的 pydantic 模型替换裸 `dict[str,Any]`（T-1/T-2），`load_profile()` 加载期校验；**新增畸形 profile/hooks 容错回归测试**
  - 依赖：无 · 风险：⚠️中（profile.yaml 失败时机前移）· 验证：`pytest tests/platform tests/hook`（含畸形用例）+ `mypy`

## 阶段 2 · 模块下沉与拆分（G3 + D-7）

低-中风险纯搬迁；可与阶段 0/1 并行。直接更新调用点，无需 re-export shim（兼容基线决策）。

- [ ] **TASK-06** `refactor: split god modules and relocate process primitives`
  - 动作：`pid_alive`+进程原语→`utils/process.py`（移除 penpot `allow-layer-dep`，S-3/L-7）；`platform/helpers.py` 拆 fileops/hooks_config/mcp_config（S-2）；`mcp/lifecycle.py` 拆 health_probe/state_store（S-3）；`core/scaffold.py` 拆 scaffold_backup（S-4）
  - 依赖：无 · 风险：低 · 验证：`run_local`（layer 守卫）+ `pytest tests/mcp tests/platform tests/core tests/integrations`
- [ ] **TASK-07** `refactor(utils): unify frontmatter parsers`
  - 动作：合并 `utils/frontmatter` 与 `kg/ingest/frontmatter`（+ `yaml_parser` 包装）为单一解析器，错误语义由参数控制（D-7）
  - 依赖：无 · 风险：中（错误语义合并需双侧测试）· 验证：`pytest tests/kg tests/skill`（覆盖 doc_consistency + kg ingest 两条路径）

## 阶段 3 · UI 反向边治理（G1）⚠️

消除 L-1/L-3/L-5 前半的 UI 反向边。建议在阶段 2 之后。内部分步：先建 `core/console.py` 端口，再逐个改造消费方（utils/cli/penpot），最后下沉 `classify_tallies`。

- [ ] **TASK-08** `feat(core): Console port and migrate UI consumers off interface` ⚠️
  - 动作：`core/console.py`（`Console` Protocol + `ChoiceOption`/`DiagPattern` + `pattern_matches`）；`interface.cli.ui` 实现该 Protocol；删 `utils/common.py` ui 包装（含 D-3）改注入 Console；penpot 注入 Console + `PENPOT_PATTERNS` 归位；`classify_tallies` 下沉 core（G1/L-1/L-3/L-5 前）
  - 依赖：TASK-06（软，模块就位后改造更顺）· 风险：⚠️中 · 验证：`run_local`（layer 守卫）+ `pytest` + 手测 `penpot`/`doctor` 交互输出

## 阶段 4 · application→interface 解耦 + feedback 上移（G4 + L-5 后半）⚠️

- [ ] **TASK-09** `refactor: doctor service and relocate feedback to application` ⚠️
  - 动作：把 `doctor_summary.py` 经 Click `CliRunner` 反向驱动 CLI 改为直接调提取出的 doctor 服务函数（L-5 后半）；随后 `core/feedback/`→`application/feedback/`、删延迟 import shim、全局改 import（G4/L-2）
  - 依赖：TASK-08（UI 边清后 feedback 不再间接拉 interface）· 风险：⚠️中 · 验证：`run_local`（layer 守卫）+ `cataforge feedback bug/suggest` 端到端 + `pytest tests/services tests/core/test_feedback`

## 阶段 5 · deploy 算法收回 runtime（G2，全量迁移）⚠️⚠️

最高破坏性，对应 `pre_dev` 检查点，整阶段单独 go/no-go。step 先 thin-delegate 旧 mixin 再内联。

- [ ] **TASK-10** `test(deploy): snapshot deploy-step and manifest behavior`
  - 动作：固化各 deploy step 与 manifest 现状行为快照，作迁移安全网
  - 依赖：无 · 风险：低 · 验证：`pytest tests/deploy` + `pytest -m slow tests/e2e/test_deploy_links_and_doctor.py`
- [ ] **TASK-11** `refactor(deploy): introduce explicit step pipeline`
  - 动作：`Deployer._deploy()` 拆为 `STEPS` 列表，仅遍历+收集 actions（C-1，暂不迁物理位置）。**这是 go/no-go 否决时的低破坏止步点。**
  - 依赖：TASK-10 · 风险：中 · 验证：全量 `pytest` + e2e
- [ ] **TASK-12** `refactor(deploy): migrate all deploy steps and template render to runtime` ⚠️⚠️
  - 动作：`_deploy_mixins/{agents,instructions,skills,commands_rules,mcp}.py`→`runtime/deploy/steps/`，改为消费 adapter；`core/template.py` `render_runtime_content`→`runtime/deploy/template_render.py`（G2.1/G2.3/L-6）；顺带消 `deploy_agents` 克隆（D-8）
  - 依赖：TASK-11, TASK-05（typed profile）· 风险：⚠️⚠️极高 · 验证：全量 `pytest` + e2e + 四端 `deploy --dry-run` 结构对比
- [ ] **TASK-13** `refactor(platform): reduce adapter to config carrier` ⚠️⚠️
  - 动作：`PlatformAdapter` 去掉 5 个 deploy mixin 多继承，降为纯 config/capability carrier + strategy hook（G2.2）
  - 依赖：TASK-12 · 风险：⚠️⚠️极高 · 验证：全量 `pytest` + e2e + `run_local`（layer 守卫应显示 adapter→runtime 反向边消失）

## 阶段 6 · 守卫收紧 + 质量收尾（G6 + §7）

低风险；守卫类需反向边清零（阶段 3/4/5 完成）后才从 warn 转 fail。

- [ ] **TASK-14** `refactor: scope module-level caches and narrow broad except`
  - 动作：5 处裸 `global` 缓存加 conftest autouse `clear_cache()` + `lru_cache`/`Lock`（Q-3）；静默 `except Exception` 收窄类型 + 补 `logger.debug`（Q-1）
  - 依赖：无 · 风险：低 · 验证：`pytest -n auto` 烟测
- [ ] **TASK-15** `ci: tighten layer guard, add import-linter, strict packages`
  - 动作：强化 `check_layer_dependencies.py`（函数内/`TYPE_CHECKING` 向上 import 纳入 allowlist 对账）；加 `[tool.importlinter]` 单向 contract；ruff `max-complexity` 20→15；逐包加 mypy strict；`pytest-cov` 基线（§7/G6）
  - 依赖：TASK-08, TASK-09, TASK-13（反向边清零）· 风险：低（先 warn）· 验证：`run_local` + `mypy` + CI `lint-imports`
- [ ] **TASK-16** `chore(skill): resolve confirmation-gated dead code`
  - 动作：待产品确认后清理 `nl_query`（D-9）、R-006 死守卫（D-10）、`governance_pydantic`（D-14）、`issue.py:255` `_TODO` 措辞（D-13）
  - 依赖：产品确认（见主方案 §8 剩余待确认）· 风险：低 · 验证：`pytest`

---

## 关键路径与并行批次

- **可立即并行启动**：TASK-01、02、03、06、07（互不依赖）；TASK-04 紧随 TASK-03；TASK-05 独立。
- **唯一长关键路径**（阶段 5）：TASK-10 → 11 → 12 → 13，其中 TASK-12 还需 TASK-05 先落。
- **守卫压轴**：TASK-15 必须等 TASK-08/09/13 把反向边全部清零，否则守卫转 fail 会立即红。
- **go/no-go 闸**：进入阶段 5 前（TASK-10 后、TASK-12 前）按 `pre_dev` 检查点人工评审；若否决，止步 TASK-11（仅 pipeline 化的低破坏增量）。

合计 16 个 task：⚠️⚠️极高 2（TASK-12/13 + 整阶段 5 闸）、⚠️中/高 3（TASK-05/08/09）、其余低-中。
