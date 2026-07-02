# 提案：code-review 框架侧静态检查审计 — 架构守护与复杂度门禁的插件式扩展

> 状态：设计提案（仅分析与设计，无代码改动）
> 范围：框架交付给下游的代码静态检查（`cataforge skill run code-review`），不含本仓自用守卫（`scripts/checks/` / `run_local.py` / CI workflow）
> 证据约定：所有结论标注到具体文件与行为；无法从源码直接证实的推断显式标注 `[推断]`

---

## 1. 现状盘点

### 1.1 入口与派发链路（已核实）

单一入口 `cataforge skill run code-review -- <args>`，链路：

1. CLI：`src/cataforge/interface/cli/skill_cmd.py` `skill_run()` — 转发 args、透传子进程退出码（保留 exit 2 等语义供 shell 管线分派）。
2. 运行器：`src/cataforge/runtime/skill/runner.py` `SkillRunner.run()` — 注入 `CATAFORGE_PROJECT_ROOT`；默认超时 300s（framework.json `constants.SKILL_RUNNER_TIMEOUT_DEFAULT_SECS` 可覆盖）；成功/超时向 `docs/EVENT-LOG.jsonl` 追加 best-effort `state_change` 记录（code-review 在 loader `_BUILTIN_EVENT_LOGGED` 集合内）。
3. 解析：`src/cataforge/runtime/skill/loader.py` `SkillLoader.get_skill()` — 优先级从高到低：override 层（user > project > scaffold `.cataforge/skills/`）→ plugin skill → package builtin（`_BUILTIN_ID_MAP` 把 `code_review` 映射为 `code-review`）。纯散文 override 无 `scripts/` 时借用 builtin 脚本（`_merge_builtin_fallback`），`record_to_event_log` 随 skill id 继承。
4. 执行：builtin 走 `python -m cataforge.runtime.skill.builtins.code_review.code_lint`；项目 override 脚本走 `python <project>/.cataforge/skills/code-review/scripts/<entry>`。

退出码协议（`code_lint.py` docstring + runner 事件映射）：0=PASS，1=有 finding（needs_revision），2=用法错误/目标缺失（blocked）。

### 1.2 双层分工

- **Layer 1（机械，`code_lint.py`）**：linter 按扩展名派发 + wiring 正则 + ui_fidelity 跨文件集合差；确定性、可豁免、有退出码。
- **Layer 2（语义，SKILL.md 散文）**：8 个维度（convention / structure / security / consistency / integration-wiring / visual-fidelity / error-handling / test-quality），进入前按 `framework.json` `project.languages` 载入 `references/lang-<lang>.md` 语言细则（现有 python / js-ts / go / rust / java / csharp 六份）。短路条件（`task_kind ∈ [chore, config, docs]`、`tdd_mode: light` + AC≤2、`--layer1-only`）与强制豁免（`security_sensitive` / `user_facing_critical_path` / `consumer_components` 非空 / Layer 1 出现 security 类 finding）见 SKILL.md §Step 2。

### 1.3 双模式

| 模式 | 类 | 触发 | 内容 | 门禁 |
|------|----|------|------|------|
| review | `CodeLinter` | 任务粒度（TDD GREEN 后） | per-file lint + wiring 扫描 + ui_fidelity 跨文件扫描 | lint error → exit 1（fail-on-error）；wiring 仅 WARN；ui_fidelity `dead_token` FAIL、其余 WARN |
| scan | `CodeScanner` | 项目级巡检（按需，不进 TDD 主循环） | 先跑完整 lint pass，再按 `--focus` 跑 `SCAN_PROBES` | **只因 lint error FAIL**；rot probe finding 一律 informational（`code_lint.py` 行 512-518 注释明示） |

`--focus` 校验只存在于 scan 模式（`VALID_FOCUS = SCAN_PROBES.keys()`）。**review 模式脚本只识别 `--fix`，SKILL.md §维度收敛的 `--focus security,error-handling` 是 Layer 2 AI 约定，Layer 1 脚本静默忽略该参数**（`main()` 仅检查 `"--fix" in sys.argv`）。

### 1.4 现状能力矩阵

| 检查项 | category | 语言 | 层 | 模式 | 门禁 | 承载插件点 |
| -------- | ---------- | ------ | ---- | ------ | ------ | ----------- |
| ESLint / Prettier | convention | js/ts/jsx/tsx | L1 | review+scan | fail-on-error | `LINTERS` 注册表 |
| Ruff check+format | convention | py | L1 | review+scan | fail-on-error | `LINTERS` |
| dotnet format | convention | cs | L1 | review+scan | fail-on-error | `LINTERS` |
| golangci-lint | convention | go | L1 | review+scan | fail-on-error | `LINTERS` |
| cargo clippy | convention | rs | L1 | review+scan | fail-on-error | `LINTERS` |
| 工具缺失降级 | — | 全部 | L1 | review+scan | WARN 跳过 | `tool_available()` |
| wiring 空 handler | integration-wiring | js-ts(3 条)/java(3)/go(2)/csharp(2)/rust(3)；python 0 条 | L1 | review | WARN | `rules/wiring-{lang}.yaml`（rule_type=wiring） |
| ui_fidelity dead_token | structure/visual | css/scss/markup | L1 跨文件 | review+scan | **FAIL** | `ui_fidelity.py`（无 YAML 面） |
| ui_fidelity unloaded_font / ghost_class | visual | 同上 | L1 跨文件 | review+scan | WARN | 同上 |
| duplication: jscpd / pmd-cpd | duplication | 多语言 / java | L1 probe | scan | informational | `SCAN_PROBES` |
| dead-code: vulture / ts-prune / knip / cargo-machete | dead-code | py / ts / ts+svelte / rs | L1 probe | scan | informational | `SCAN_PROBES` |
| complexity: radon(-n C) / gocyclo(-over 15) / eslint(complexity 10) | complexity | py / go / js-ts-svelte | L1 probe | scan | **informational**，阈值硬编码在命令行 | `SCAN_PROBES` |
| 8 维语义审查 | 全 category | 全部 | L2 | review | 三态判定（COMMON-RULES §三态判定逻辑） | SKILL.md 散文 + `references/lang-*.md` |
| rot 严重度聚合（cc≥20→HIGH 等） | complexity 等 | 全部 | L2 | scan | informational | SKILL.md scan §Step 2 散文 |

### 1.5 既有插件点（a–d，逐一核实）

1. **(a) 代码注册表**：`LINTERS`（list[dict]，extensions→tools）与 `SCAN_PROBES`（category→probe dict，含 `detect` / `build_cmd` / `fail_on_nonzero`），位于 `code_lint.py`。声明式增删，但是 **Python 源码内部结构** — 下游无法只加一个 probe 而不整体 override 脚本。
2. **(b) `CHECKS_MANIFEST` 契约**：`builtins/code_review/__init__.py`，9 条目（6 linter + tool_missing + wiring + ui_fidelity），字段 `id` / `title` / `severity`。framework-review B3-α（`framework_review/checks/b3.py`）对账 SKILL.md `## Layer 1 检查项` 段：锚点模式（`<!-- check_id: ... -->` 双向对账）或委托模式（`权威清单见 ...CHECKS_MANIFEST`）；code-review SKILL.md 当前用委托模式。**`SCAN_PROBES` 不在 manifest 内** — scan probe 的 SKILL.md 散文清单无机器对账。
3. **(c) rules YAML 插件**：`runtime/skill/rules/loader.py` — `CURRENT_SCHEMA_VERSION=1`；`register_rule_type()` 是 rule_type 注册点（现有 `wiring` / `e2e` / `doc_terms`），schema 只约束 pattern 键（`{regex, flags?, label?}`），其余键透传 `RuleSpec.raw` 由消费方解释；解析优先级 package 默认 < scaffold `skills/<id>/rules` < override 层，按 `(rule_type, language)` 覆盖；B3-β 用同一 `validate_yaml_text` 校验项目 YAML。
4. **(d) 门禁语义**：lint fail-on-error；wiring WARN；ui_fidelity 按 finding 分级；scan probe informational。例外机制三层：任务卡字段（`wiring_placeholder: true`）、文件级 pragma（`// cataforge: wiring-placeholder`、`cataforge-allow-ui-fidelity`）、Layer 2 短路豁免字段。

### 1.6 同族 skill 边界（SKILL.md frontmatter description + B3 `_BUILTIN_MAP`）

- doc-review：docs/ 文档产物；framework-review：`.cataforge/` 元资产（含 B3 对本 skill 的对账）；sprint-review：Sprint 完成度 / AC 覆盖（code-review test-quality 维度显式不重复 AC 覆盖）；task-dep-analysis：任务依赖图。code-review 限 src/ 业务代码。

---

## 2. 差距矩阵

| # | 缺失维度 | 现状证据 | 下游风险 | 优先级 |
| --- | --------- | --------- | --------- | ------- |
| G1 | **架构守护（依赖方向 / 分层 / 模块边界）完全缺失** | Layer 1 无任何 import 图检查；Layer 2 `structure` 维度是散文、任务粒度、无全局视野。对照：本仓自身有 `scripts/checks/check_layer_dependencies.py`（interface→application→{runtime,domain}→adapter→core→utils 方向守卫 + allowlist + `# allow-layer-dep` 逃生口），**但它是元项目自用，不交付下游** | LLM 为修一个 bug 顺手加一条便利 import，分层被静默击穿；数月后循环依赖不可拆 | **P0** |
| G2 | **复杂度无门禁** | complexity 仅 scan 模式 informational；阈值硬编码在 probe 命令行（radon `-n C`、gocyclo `-over 15`、eslint `10`），不可配置；review 模式对新增 500 行巨型函数零信号（lint 通过即 PASS）；无认知复杂度；SKILL.md scan §Step 2 的严重度映射（cc≥20→HIGH）与 probe 阈值双源、可漂移 | LLM 反复 patch 同一函数，复杂度单调爬升永不触发任何 gate | **P0** |
| G3 | scan probe 无 manifest 对账 | `CHECKS_MANIFEST` 只含 review 检查；SKILL.md "scan 模式额外的腐化 probe" 段落纯散文 | probe 增删后 SKILL.md 漂移，framework-review 抓不到 | P1 |
| G4 | 无基线 / 棘轮（ratchet） | scan 报告是时点快照（`CODE-SCAN-{YYYYMMDD}`），无与上次比较 | informational finding 永远不转化为行动；rot 单调累积 | P1 |
| G5 | 公共 API 契约漂移无检查 | 无导出面快照/diff；ts-prune 的"未引用导出"仅 LOW 提示 | LLM 重命名/删除导出符号，下游消费者静默断裂 | P1 |
| G6 | 注册表不可声明式扩展 | `LINTERS` / `SCAN_PROBES` 是脚本内 Python 字典；下游想加 probe 只能整体 override `code_lint.py`，失去上游升级 | override 脚本随框架升级腐化 | P2 |
| G7 | 例外治理缺失 | 三类 pragma / 任务卡豁免无 inventory、无 aging；`wiring_placeholder` 关联 backlog ID 只是散文约定 | 豁免只增不减 — 豁免蔓延本身即 LLM 腐化形态 | P2 |
| G8 | review 模式参数校验弱 | `--focus` 在 review 模式被脚本静默忽略（§1.3） | 调用方以为收敛了 Layer 1 范围，实际全量跑 | P2 |
| G9 | 其他 LLM 腐化形态无机械探针 | 配置死键（声明的 config key 零读取，`dead_token` 的配置版）、平行重复实现（jscpd 只抓文本克隆）、模块体积爬升 | 形式契约满足但结构腐化 | P2 |

---

## 3. 插件式扩展方案

### 3.0 总原则

1. 全部新检查经 `cataforge skill run code-review -- <args>` 现有入口调起，不加新 CLI 动词。
2. 声明式规则一律走 (c)：`register_rule_type()` 注册新 rule_type，YAML 沿用 `schema_version` / `rule_type` / `language` / `extensions`，下游在 `.cataforge/skills/code-review/rules/` override，B3-β 自动获得校验。
3. 检查内核语言无关；语言细节（import 语法、函数声明形态、导出语法）只以 YAML pattern（带 `label`）承载，识别模式细则与反例写 `docs/reference/`（遵循本仓硬约束 2），SKILL.md 主体链接引用。
4. 每个新检查同步进 `CHECKS_MANIFEST`；manifest schema 增补 `modes` 字段一并修复 G3。
5. 门禁语义显式声明；默认遵循"**确定性契约违反 → gating，统计性 rot 信号 → informational + 棘轮**"。

### 3.1 基础设施变更（一次性，服务所有新检查）

1. **`CHECKS_MANIFEST` 条目增补可选字段** `modes: "review" | "scan" | "review+scan"`（缺省 `review+scan`，向后兼容），并把现有 `SCAN_PROBES`（jscpd / pmd-cpd / vulture / ts-prune / knip / cargo-machete / radon / gocyclo / eslint-complexity）补录为 `severity: informational`、`modes: scan` 条目。B3-α 委托模式无需改动；补一条单测断言 `SCAN_PROBES` 每个 probe name 在 manifest 有对应条目（放 `tests/skill/`，与既有 `_BUILTIN_MAP` 完整性测试同风格）。
2. **loader 增加可选结构校验回调**：`register_rule_type(name, *, list_pattern_keys, single_pattern_keys=None, extra_validator=None)` — `extra_validator(raw, source)` 校验该 rule_type 的非 pattern 结构键（如 arch 的 `layers`）。B3-β 调用的 `validate_yaml_text` 自动执行，项目 YAML 结构错误在 framework-review 呈现为 audit finding 而非运行期异常（与 loader docstring 既定分工一致）。
3. **`SCAN_PROBES` 支持内部 probe**：probe dict 的 `build_cmd` 允许构造 `[sys.executable, "-m", "cataforge.runtime.skill.builtins.code_review.<module>", ...]` 自调框架内核模块，`detect` 用 `[sys.executable, "--version"]` 恒真。零注册表结构改动，纯新增条目。

### 3.2 落地示例一：架构守护（新 rule_type `arch`）

**内核**：新模块 `builtins/code_review/arch_guard.py`（语言无关）：

1. 从解析到的 `arch-{lang}.yaml` 读取项目 `layers`（path glob → 层名）与 `rules`（层间允许方向），union 所有语言的模型；
2. 对目标文件用该语言 YAML 的 `import_patterns`（带 `label`，捕获组 1 = 被导入模块）提取依赖边；
3. 将 (源文件层, 目标模块层) 对照方向矩阵，违规即 finding；
4. 行级逃生口 pragma：`cataforge: allow-arch-dep(<reason>)`（reason 必填，供 §3.5 例外治理盘点）。

**零/低配置**：builtin 只随包发运 per-language 的 `import_patterns`（无 `layers`）→ 未声明分层模型时检查**静默不激活**（scan 输出一条 INFO 提示可启用）。下游启用 = 在 override 目录放一份声明 `layers` 的 YAML，一次性配置。

**YAML 样例**（下游 `<project>/.cataforge/skills/code-review/rules/arch-python.yaml`）：

```yaml
schema_version: 1
rule_type: arch
language: python
extensions: [".py"]

# 语言相关：import 依赖边提取（builtin 已发运默认，override 可增补）
import_patterns:
  - label: "import module"
    regex: '^\s*import\s+([\w.]+)'
    flags: ["MULTILINE"]
  - label: "from-import"
    regex: '^\s*from\s+([\w.]+)\s+import\b'
    flags: ["MULTILINE"]

# 语言无关：项目分层模型（声明即激活；由 extra_validator 结构校验）
layers:
  - name: interface
    paths: ["src/myapp/api/**", "src/myapp/cli/**"]
  - name: service
    paths: ["src/myapp/services/**"]
  - name: domain
    paths: ["src/myapp/domain/**"]
  - name: infra
    paths: ["src/myapp/infra/**"]

# 方向矩阵：每层只能 import 自身或所列层；未列出即违规
rules:
  interface: [service, domain]
  service: [domain, infra]
  domain: []
  infra: []
```

**接线**：

1. review 模式：`CodeLinter.run()` 末尾新增跨文件步骤（与 `scan_ui_fidelity()` 同位同形：target 文件的出边为受检对象，corpus 全项目解析层归属）；
2. scan 模式：`SCAN_PROBES` 新增 category `"arch"`（内部 probe，§3.1-3），`--focus arch` 可单独跑；
3. `CHECKS_MANIFEST` 新增 `{"id": "code_lint.arch_guard", "severity": "fail-on-error", "modes": "review+scan"}`；
4. 语言识别细则与各语言 import 形态反例写 `docs/reference/arch-checks.md`，SKILL.md 主体仅链接（同 `wiring-checks.md` 先例，实际位于 `.cataforge/references/`）。

**门禁语义**：违反已声明的方向矩阵是确定性契约违反 → review 与 scan 均 **fail-on-error**（arch 挂在 lint pass 内，天然继承 scan "仅 lint error FAIL" 的既有语义，无需改 `CodeScanner` 判定）。首个启用版本建议提供 YAML 级开关 `enforce: warn | fail`（默认 `fail`；迁移期可设 `warn` 影子运行一个 Sprint）。

**framework-review 自洽验证**：B3-α 委托模式覆盖 manifest 新条目；B3-β 经 `extra_validator` 校验下游 `arch-*.yaml` 的 `layers`/`rules` 结构（未知层名、方向矩阵引用未声明层 → FAIL finding）。

### 3.3 落地示例二：复杂度门禁（新 rule_type `complexity`）

**内核**：新模块 `builtins/code_review/complexity_gate.py`（语言无关）：

1. 阈值外置到 `complexity-{lang}.yaml`（builtin 发运保守默认，下游 override 收紧/放宽），消除 G2 的硬编码与双源；
2. 度量获取两级：优先适配已装工具（复用/参数化现有 radon / gocyclo / eslint probe；可选增补 lizard 作为多语言圈复杂度兜底 — 工具适配清单是 skill 能力声明，属硬约束 2 合法例外）；工具全缺时退化到 YAML 驱动的代理度量（`function_start_patterns` 定位函数边界 + 嵌套深度 / 函数行数 — 语言细节全在 pattern，内核只数行与缩进）；
3. **棘轮基线**：`.cataforge/baselines/complexity.json`（函数级指纹 → 度量值）。scan 刷新基线；review 只对 **git diff 涉及的函数** 施门禁，且判据为 `max(fail 阈值, 基线值)` — 改到的函数不得比基线更差，legacy 未触碰不阻塞；
4. 行级逃生口 `cataforge: allow-complexity(<reason>)`。

**YAML 样例**（builtin 默认 `rules/complexity-python.yaml`）：

```yaml
schema_version: 1
rule_type: complexity
language: python
extensions: [".py"]

# 代理度量的函数边界定位（工具缺失时的兜底路径）
function_start_patterns:
  - label: "def"
    regex: '^\s*(?:async\s+)?def\s+\w+'
    flags: ["MULTILINE"]

# 语言无关阈值（warn 报告不阻塞；fail 在 review 模式对 diff 涉及函数阻塞）
thresholds:
  cyclomatic: { warn: 10, fail: 15 }
  cognitive: { warn: 15, fail: 25 }
  function_lines: { warn: 60, fail: 120 }
  nesting_depth: { warn: 4, fail: 6 }
```

**接线**：

1. review 模式：`CodeLinter.run()` 新增 per-file 步骤（同 `scan_wiring` 位）；超 `fail` 且劣于基线 → `self.errors += 1`；超 `warn` → WARN；
2. scan 模式：现有 `SCAN_PROBES["complexity"]` 的三个 probe 改为从 YAML 读阈值构造命令（radon `-n` 档位、gocyclo `-over`、eslint rule 数值），并新增内部 probe 负责聚合 + 基线刷新；SKILL.md scan §Step 2 的严重度映射改为委托 YAML 阈值（消除双源）；
3. `CHECKS_MANIFEST` 新增 `{"id": "code_lint.complexity_gate", "severity": "fail-on-error", "modes": "review"}` 与 `{"id": "code_lint.complexity_trend", "severity": "informational", "modes": "scan"}`；
4. 认知复杂度权重表、各语言分支关键字清单写 `docs/reference/complexity-checks.md`。

**门禁语义**：review 对**增量**（diff 涉及函数）fail-on-error，存量仅棘轮；scan 全库 informational + 基线刷新。这与 SKILL.md Anti-Patterns "scan 不因腐化 finding 判 needs_revision" 完全兼容 — gating 只发生在 review 模式的增量上。

### 3.4 后续探针（同一机制，简述）

| 新检查 | rule_type / 插件点 | 门禁 | 针对腐化形态 |
| -------- | ------------------- | ------ | ------------- |
| api-surface（导出面快照 diff） | `api-surface-{lang}.yaml`（导出声明 pattern）+ 内部 scan probe + `.cataforge/baselines/api-surface.json` | informational，YAML `gating: true` 可升级 | 公共 API 契约静默漂移（G5） |
| config-consistency（配置死键） | 复用 `ui_fidelity` 集合差内核泛化：声明 pattern × 消费 pattern 两组 YAML 键 | scan informational | 声明了但零读取的 config key / feature flag（G9） |
| pragma-inventory（豁免盘点） | 内部 scan probe：枚举全部 `cataforge:` 豁免 pragma + reason + 引入 commit 时间（git blame），报告 aging | scan informational | 豁免蔓延（G7） |

### 3.5 Layer 2 配套（最小改动）

1. SKILL.md `structure` 维度补一句：以 Layer 1 arch_guard 报告为输入，语义判定聚焦机械抓不到的越层（如 interface 层内嵌业务规则但无 import 信号）；
2. scan §Step 2 严重度映射改为引用 complexity YAML 阈值（删除散文里的硬编码数值）；
3. `--focus` 语义修复（G8）：review 模式脚本对未知 flag 报 exit 2，`--focus` 值透传给新增的 arch / complexity 步骤做维度收敛，与 Layer 2 维度收敛对齐。

---

## 4. 腐化防护论证（下游 LLM 主导开发的失效场景）

| # | 失效场景 | 无防护时的长期后果 | 对应检查 | 机械可判定 vs 须 Layer 2 |
| --- | --------- | ------------------- | --------- | ------------------------ |
| S1 | LLM 修 bug 时从底层模块反向 import 上层的便利函数 | 分层静默击穿 → 循环依赖 → 模块不可独立测试/替换 | arch_guard（review 即 FAIL，pragma 需 reason） | **机械**：import 边方向是确定性事实。"这个职责该不该放这层"（无 import 信号的语义越层）→ L2 structure |
| S2 | LLM 每轮对同一函数追加 if 分支而非重构 | 圈/认知复杂度单调爬升，最终任何修改都引发回归 | complexity_gate 棘轮（改到即不得更差） | **机械**：阈值与基线比较。"这次超标是否本质复杂度、拆分方案是否合理" → L2 |
| S3 | LLM 不知道已有实现，重新生成一份平行 util | 双实现漂移，修 A 漏 B | jscpd/pmd-cpd（文本克隆，scan informational）+ 基线趋势使增量可见 | 文本克隆机械；**语义近似克隆（同逻辑不同措辞）只能 L2** consistency/duplication |
| S4 | handler 形式接线但函数体为空 / 占位返回，类型契约全绿 | user-facing 路径静默失效 | 既有 wiring（L1 WARN）+ L2 integration-wiring 强制豁免路径（`consumer_components` 非空禁止短路） | 空体模式机械；"返回值是否真实业务语义而非占位常量" → L2 |
| S5 | 豁免 pragma（wiring-placeholder / allow-arch-dep / allow-complexity）只增不减 | 守卫被合法逃生口架空 | pragma-inventory（aging 报告进 CODE-SCAN，reason 必填） | 盘点机械；"该豁免是否仍成立"须人/L2 判定 |
| S6 | LLM 重命名导出符号顺手"清理"公共 API | 下游消费者静默断裂 | api-surface 快照 diff | diff 机械；"这算破坏性变更还是内部符号" → L2 + 项目 YAML gating 声明 |
| S7 | 设计 token / config key 声明后无人消费 | 死配置累积，读者无法分辨哪些生效 | 既有 ui_fidelity dead_token（FAIL）+ config-consistency 泛化 | **机械**：集合差 |
| S8 | scan 报告年年产出、无人行动 | informational 信号疲劳，rot 正常化 | 棘轮基线把"绝对量报告"变为"增量不得恶化"的 review 门禁 | 机械（基线比较）；重构优先级排序 → L2 / sprint 决策 |

**边界总结**：Layer 1 收编所有"集合差 / 正则模式 / 阈值-基线比较 / 图方向"类确定性判定并给出退出码门禁；Layer 2 保留"意图与合理性"判定（抽象是否得当、重复是否故意、复杂度是否本质、豁免是否仍有效），且以 Layer 1 finding 为输入而非重复扫描。gating 的铁律是**只对确定性契约违反和增量恶化阻塞**，避免 LLM 修复循环被统计性误报打断。

---

## 5. 分阶段路线图

| 阶段 | 内容 | 验收信号 | 下游迁移成本 |
| ------ | ------ | --------- | ------------- |
| M1 基础设施 | manifest 增 `modes` 字段 + 补录 SCAN_PROBES 条目；loader `extra_validator`；probe 阈值外置到 complexity YAML（仅参数化，未 gating） | framework-review B3 全 PASS；新单测（SCAN_PROBES↔manifest 对账）绿；scan 输出阈值来源为 YAML | **零**（默认值不变） |
| M2 架构守护 | rule_type `arch` + `arch_guard.py` + review/scan 接线 + `enforce: warn | fail` + `docs/reference/arch-checks.md` | fixture 项目（含一条违规 import）review exit 1；未声明 layers 的项目行为不变；B3-β 抓坏 YAML | **opt-in**：不声明模型零影响；启用 = 一份 YAML |
| M3 复杂度门禁 | `complexity_gate.py` + diff 增量判定 + 基线棘轮 + scan 基线刷新 | 触碰超 fail 阈值函数的 review FAIL，未触碰 legacy PASS；连续两次 scan 基线差异 = 期间 diff | **低**：默认阈值保守 + 棘轮免除存量 + pragma 逃生 |
| M4 扩展探针 | api-surface / config-consistency / pragma-inventory（均 scan informational） | CODE-SCAN 报告出现三类新 section；pragma 盘点含 reason 与 aging | **零**（informational） |
| M5 语义收口 | SKILL.md L2 维度对接 L1 新报告；scan §Step 2 阈值去双源；`--focus` review 模式修复 | B3-α 委托对账 PASS；review 模式未知 flag exit 2 | 零 |

每阶段独立成 PR（conventional-commits，scope `skill`），符合最小可行修改 — SKILL.md 改动只写规则本身。

---

## 6. 关键权衡与风险

1. **误报率 vs 解析深度**：import/导出提取用正则而非语言 parser — 动态 import、re-export、字符串拼接模块名会漏/误。取舍：正则保持内核语言无关与零依赖（与 wiring/e2e 先例一致）；缓解 = `enforce: warn` 影子期 + 行级 pragma + 把已知盲区写进 `docs/reference/arch-checks.md` 声明为 L2 职责。**不追求静态完备，追求"常见腐化路径确定性拦截"**。
2. **探针性能与超时预算**：SkillRunner 默认总超时 300s，probe 各 180s、lint 单文件 60s — scan 已接近预算上限；arch/complexity 内核是纯 Python 文件遍历（复用 `_iter_files` + `EXCLUDE_DIRS` 剪枝），必须保持 O(files) 单遍；大仓建议文档化调高 `SKILL_RUNNER_TIMEOUT_DEFAULT_SECS`。基线文件把全库度量成本摊销到 scan，review 只算 diff 函数。
3. **语言解耦边界**：内核只允许出现"层 / 边 / 阈值 / 基线"抽象；任何语言关键字（import 形态、函数声明、导出语法）必须下沉 YAML pattern 或 `docs/reference/`。风险是代理度量（缩进嵌套深度）对某些语言失真（如 go 的 gofmt 强制风格使其可靠，模板语言则不然）— 以工具适配优先、代理度量兜底并在报告标注度量来源。
4. **例外治理**：逃生口是守卫可用性的前提，也是被架空的通道。三道闸：reason 必填（无 reason pragma 视为违规本身）、pragma-inventory 盘点 aging、framework-review 可后续增加"豁免数量阈值"audit finding。
5. **gating vs informational 的取舍**：过度 gating 会让下游 LLM 陷入"改 A 触发 B 门禁"的 thrash；过度 informational 则重蹈 G4/S8。本方案的分界线 = **确定性 + 增量**：确定性契约违反（arch 方向、声明阈值+基线恶化、dead_token）才 gating，且复杂度只 gating 触碰到的函数；统计性信号（克隆率、死码量、趋势）一律 informational + 棘轮呈现。
6. **schema 演进**：新 rule_type 均为增量注册，`schema_version` 维持 1（per-type 键由 `extra_validator` 各自管辖）；仅当 loader 顶层契约（必填四键）变更才 bump 并提供迁移检查（framework.json `migration_checks` 面已有承载）。
7. **基线文件的事实源风险** `[推断]`：`.cataforge/baselines/*.json` 入 git 后可能被 LLM 顺手"修基线过门禁"。缓解：基线只允许由 scan 写入（review 只读），framework-review 增加"基线变更须伴随 scan 报告"的对账项 — 具体机制留 M3 设计。
