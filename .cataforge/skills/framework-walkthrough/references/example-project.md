# 走查示例目标库

本文件定义 framework-walkthrough 内置的示例目标。示例的唯一职责是**驱动工作流主干跑一遍**，不追求业务复杂度。

## 示例目标合格性清单

自带目标替换内置目标时，逐条自检：

- **单轮收敛**：在一个会话内能从需求走到评审通过，不需要多 Sprint 迭代。
- **触达主干**：能产生需求项、至少一个架构组件/契约、至少一个可 TDD 的纯逻辑单元、可评审的产物。
- **确定性可验证**：验收标准是确定的输入→输出映射，便于 TDD 断言，不依赖网络/时钟/随机。
- **低依赖**：核心逻辑无外部服务/数据库/重型依赖，便于在沙盒里即时跑测试。
- **语言中立可落地**：目标本身不绑定语言；代码用沙盒项目的默认语言落地（本仓默认 Python + pytest，下游按其 `project.languages`）。

## 内置目标：temperature-converter

一句话目标：实现一个温度单位转换命令行工具，支持摄氏度(C)/华氏度(F)/开尔文(K)三种单位互转。

### 功能项（喂给 prd / prd-lite / brief）

| id | 功能 |
|----|------|
| F-001 | 摄氏 ↔ 华氏 互转 |
| F-002 | 摄氏 ↔ 开尔文 互转；华氏 ↔ 开尔文 经规范化中转 |
| F-003 | CLI 接受 `<value> <from_unit> <to_unit>`，输出转换结果（保留 2 位小数） |
| F-004 | 非法输入（未知单位 / 非数值 / 低于绝对零度）报错并以非零码退出 |

非功能：核心为纯函数、无外部依赖、结果确定。

### 架构契约（喂给 arch / arch-lite）

| id | 组件 / 契约 |
|----|------------|
| C-001 | conversion-core：纯函数层，所有转换先归一化到开尔文再转目标单位 |
| C-002 | cli-adapter：解析参数 → 调 core → 格式化输出 / 错误处理；不含转换数学 |
| API-001 | `convert(value, from_unit, to_unit) -> number`；单位 ∈ {C, F, K}；归一化后开尔文 < 0 视为低于绝对零度，抛领域错误 |

### 任务分解（喂给 dev-plan / dev-plan-lite）

| id | 任务 | 依赖 | TDD |
|----|------|------|-----|
| T-001 | conversion-core 转换逻辑 | — | light（纯逻辑，AC 表驱动） |
| T-002 | cli-adapter 参数解析与输出格式化 | T-001 | light |
| T-003 | 错误路径：未知单位 / 非数值 / 低于绝对零度 | T-001 | light |

喂 dev-plan 时 T-001 须带 `consumer_components: [cli-adapter]`（T-002/T-003 消费 core）——使 C-7 即时 per-task code-review 在 CLI 配置结构性可达；否则三任务全延迟、叠加 B-4 短路后 code-review 全程零触发。T-002/T-003 不带触发 flag，保持「延迟到 sprint-review」侧同样被观察。

dispatch 喂 tech-lead 时显式声明：**任务数恰为本示例任务表所列，不自主追加 validation / 辅助任务**——CLI 示例恰 3 个（T-001~T-003，任务数一旦超过 `SPRINT_REVIEW_MICRO_TASK_COUNT` 就击穿 B-4 短路结构）；UI 示例恰 4 个（T-001~T-004，走 B-15 正常路径，与 B-4 互斥对偶）。

### 验收标准（TDD 断言锚点）

锚点归属：核心转换数学归 T-001（断言 `convert()` 返回值），输出格式（两位小数字符串）归 T-002，错误路径 3 条归 T-003——per-task AC 保持 ≤6，避免触发 task-decomp「AC > 6 必拆」把任务数推过 `SPRINT_REVIEW_MICRO_TASK_COUNT`、意外击穿 B-4 短路结构。

正常路径：

- `0 C F` → `32.00`
- `100 C F` → `212.00`
- `-40 C F` → `-40.00`（C 与 F 的交汇点）
- `0 C K` → `273.15`
- `-273.15 C K` → `0.00`（绝对零度）
- 同单位 `25 C C` → `25.00`
- 往返一致性：`convert(convert(x, C, F), F, C) ≈ x`

错误路径：

- `-300 C K` → 报错「低于绝对零度」+ 非零退出
- `10 C X` → 报错「未知单位」+ 非零退出
- `abc C F` → 报错「非数值」+ 非零退出

testing 阶段（standard）集成面约束：CLI 进程级 4 条用例（3 条错误路径 + 1 条正常路径），不再扩展——qa-engineer 对纯函数示例过度展开集成矩阵是纯 token 开销，阶段编排本身才是观察对象。

### 为何选它

纯函数 + 表驱动 AC，让 TDD 阶段有真实而不繁的断言面；C-001/C-002 两组件让架构与 dev-plan 阶段有可拆分的实质内容；错误路径覆盖边界条件评审；全程无 I/O 与外部依赖，沙盒内可即时验证、单轮收敛。

## UI 扩展目标：temperature-converter-ui

`--example temperature-converter-ui` 在 CLI 目标全部内容之上叠加一个极小 web UI，使 ui_design 阶段真被驱动（路径 B-13）而非恒 N/A。仍满足合格性清单：静态单文件页面、无构建工具、无外部依赖、单轮收敛。

### 功能与契约增量

| id | 增量 |
|----|------|
| F-005 | 单页 web UI：数值输入 + 源/目标单位选择 + 转换结果显示 + 错误提示区（复用 conversion-core 同等转换逻辑） |
| C-003 | web-adapter：静态单页（标记 + 样式 + 挂接逻辑），不含转换数学；转换与校验规则与 API-001 同源 |
| UI-001 | 输入区：数值框 + 两个单位选择控件 |
| UI-002 | 结果区：转换结果文本，字号消费 `--result-size` token |
| UI-003 | 错误提示区：非法输入时可见，前景色消费 `--error-color` token；合法输入时不可见 |
| T-004 | web UI 层（依赖 T-001 的转换规则；`user_facing_critical_path: true`，触发 code-review ui_fidelity / visual-fidelity） |

### UI 保真验收标准（按 `.cataforge/references/fidelity-ac.md` 断言渲染效果）

- 输入 `-300` C→K 后，错误提示元素渲染可见且**计算前景色** = `--error-color` 设计值；合法输入后该元素不可见。
- 结果元素**计算字号** = `--result-size` 设计值。
- 两个 token 各被 ≥1 处真实消费（无死 token / 幽灵类）。
- 反例（不得这样写 AC）：「样式表含 `--error-color` 变量名」「结果元素带 `result-text` 类名」——字面存在即过关、渲染为空也全绿。

沙盒无头环境取不到渲染证据时，reviewer 对 T-004 应出 `conditional_release` + 非空 `blocking_conditions`（条件=补一次真实渲染核验），不得以 `[ENV-LIMITATION]` 豁免——这本身即 B-13 的观察点。

## 探针扰动（`--depth full`）

`--depth full` 要触发分支/异常路径时，对本示例做下列最小扰动即可确定性命中目标路径（路径 id 见 [`runtime-flow-map.md`](runtime-flow-map.md)，探针表见 [`walkthrough-protocol.md`](walkthrough-protocol.md) §6）。每个探针触发一条路径就够，记录行为后恢复主干。

| 目标路径 | 扰动 | 触发点 |
|---------|------|--------|
| B-3 Approved-with-Notes | arch(-lite) 里 C-001 不写「先归一化到开尔文」这条非功能约束，留作 MEDIUM | doc-review arch |
| B-4 Sprint Review 短路 | 不扰动——仅 CLI 示例：3 个任务恰 ≤ `SPRINT_REVIEW_MICRO_TASK_COUNT`，主干即命中；UI 示例 4 任务走 B-15 正常路径，二者互斥对偶 | development 收口 |
| B-5 Parallel Dispatch | dev-plan(-lite) 把 T-002、T-003 都只依赖 T-001、互不依赖、归同一 sprint_group | dev_planning |
| B-6 Change Request | development 开始前提交一句「F-003 输出改保留 1 位小数」 | development 前 |
| B-7 模式回退 | 让 prd-lite 写到 >150 行（如把每个错误码展开成段）；仅 `--mode agile-lite` 可触发 | planning |
| E-1 Interrupt-Resume | 派发 dev_planning 的 tech-lead（subagent）时不预先给定 Sprint 划分偏好与 TDD 档位期望，诱发 needs_input 回传（inline 阶段的 AskUserQuestion 澄清是预期行为、不属 E-1；判级依赖型——agent 自行 `[ASSUMPTION]` 未提问时记 not-reached） | dev_planning |
| C-6 TDD 升档 | dev-plan 阶段把 T-003 标 `security_sensitive: true` → TDD 升 standard 档（RED/GREEN 分离）+ 触发即时 code-review 且强制 Layer 2；REFACTOR 仍按 `TDD_REFACTOR_TRIGGER` 条件触发，未命中记 not-reached | dev_planning |
| E-2 Revision | arch(-lite) 首版漏掉 API-001 的「归一化后开尔文 < 0 抛领域错误」契约（CRITICAL） | doc-review arch |
| B-13 ui_design 真驱动 | 不是扰动——改用 `--example temperature-converter-ui`（UI 增量见上节） | ui_design 起 |
| B-14 Capability Gate 降级 | Bootstrap 时设计工具选 penpot（沙盒无 penpot MCP），进 ui_design 触发 gate；观察降级后选「纯文本手工 ui-spec」 | ui_design 前 |

不在表内的异常路径（E-3 rolled-back / E-4 TDD blocked / E-5 crash / E-6 truncation / E-7 cascade 中断）**不做破坏注入**：人为制造崩溃会偏离真实行为、污染归因，按机会观察处理，未触发则账本标 not-reached。
