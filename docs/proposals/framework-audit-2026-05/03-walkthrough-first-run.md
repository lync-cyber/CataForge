# framework-walkthrough 首次运行报告（改进建议初稿）

> 这是新增 skill `framework-walkthrough` 的首次端到端运行产出，作为交付物 3 的「框架/走查改进建议初稿」归档。
> skill 的**运行时**输出路径是 `docs/reviews/framework/FRAMEWORK-REVIEW-walkthrough-{date}-r{N}.md`（该目录在本仓 gitignored，属运行产物）；本文件是为评审落库的可提交副本。
> 全部 finding 均在隔离沙盒 `walkthrough-sandbox/claude-code-agile-lite/`（gitignored）内实测复现，附真实命令与退出码。

## 1. 走查配置

| 项 | 值 |
|----|----|
| 平台 | claude-code（四端中验证最充分，首跑用它以免混淆框架问题与平台问题） |
| 执行模式 | agile-lite |
| 示例目标 | temperature-converter（C/F/K 互转 CLI，见 skill references/example-project.md） |
| 落地语言 | Python 3.x + pytest |
| cataforge 版本 | 0.6.0 |
| 部署命令 | `cataforge setup`（部署 `.cataforge/` + `.claude/`） |

## 2. 阶段时间线

| 阶段 | 做了什么 | 真实命令 | 产物 | 观察点（期望 vs 实际） |
|------|---------|---------|------|----------------------|
| 部署 | 沙盒内初始化框架资产 | `cataforge setup` | `.cataforge/` + `.claude/`（agents/skills/rules/settings/commands） | ✅ 全量部署成功；含新增的 `framework-walkthrough` skill |
| 健康 | 环境体检 | `cataforge doctor` | — | ✅ 通过 |
| 需求 | 按 prd-lite 模板填 F-001..F-004 | LLM 写 `docs/prd-lite.md` | prd-lite | ⚠️ 无 CLI 生成器，纯 LLM 按模板写（见 FW-4） |
| 架构 | 按 arch-lite 填 M-001/M-002/API-001 | LLM 写 `docs/arch-lite.md` | arch-lite | 同上 |
| 任务分解 | 按 dev-plan-lite 填 T-001..T-003 | LLM 写 `docs/dev-plan-lite.md` | dev-plan-lite | 同上 |
| 索引 | 注册文档与交叉引用 | `cataforge docs index` | `.doc-index.json` | ✅ EXIT=0，文档数 4 / 交叉引用 10，deps 正确解析 |
| 文档评审 | 三份 lite 文档 Layer-1 | `cataforge skill run doc-review -- prd\|arch\|dev-plan docs/*.md` | — | ❌ 三份全 FAIL（EXIT=1），见 FW-1/2/3 |
| TDD | 写失败测试→实现→跑绿（conversion-core 表驱动 AC + CLI + 错误路径） | `python -m pytest -q` | `tempconv/` + `tests/` | ✅ 16 passed |
| 代码评审 | 核心包健康扫描 | `cataforge skill run code-review -- scan tempconv` | — | ✅ RESULT: PASS，0 findings（3 探针因工具未装跳过） |

主干结论：部署 / 索引 / TDD / code-review **跑通**；doc-review 在 agile-lite + KG-active 下对忠实填写的 lite 文档**系统性 FAIL**——这是真实框架缺陷，非走查操作失误（见 §5 自我校准）。

## 3. framework findings（框架本身）

### [W-001] HIGH: agile-lite 文档注定无法通过 doc-review Layer-1
- **category**: consistency
- **root_cause**: self-caused
- **描述**: lite 模板 front-matter 的 `doc_type` 是 `prd`/`arch`/`dev-plan`（非 `-lite`），doc-review 据此施以**完整 standard 层检查**：prd 要求「用户故事」（实测 `FAIL: 4个功能仅0个有用户故事`）、「非功能章节过短」；arch 要求「API request 定义」（`FAIL: 1个API中1个缺少request定义`）。但 lite 模板结构本就不含用户故事 / API request 字段 → 任何忠实按 lite 模板填写的文档必 FAIL。这与 COMMON-RULES §执行模式矩阵「agile-lite：Layer 1 强制」形成"强制但注定挂"的矛盾。
- **建议**: 二选一——(a) lite 模板补齐这些字段；(b) doc-review 按 `mode: agile-lite` / `-lite` doc_type 派生一组放宽的 Layer-1 规则。涉模板 + doc_review checker，需多文件改动。

### [W-002] HIGH: DOC_REVIEW_L2_SKIP_DOC_TYPES 三方不一致（dead config）
- **category**: dead-code
- **root_cause**: self-caused
- **描述**: 常量 `DOC_REVIEW_L2_SKIP_DOC_TYPES = [brief, prd-lite, arch-lite, dev-plan-lite, changelog]`，但：① lite 模板实际 `doc_type` 为 `prd/arch/dev-plan`；② doc-review Layer-1 不认识 `prd-lite`——实测 `doc-review -- prd-lite docs/prd-lite.md` 返回 `WARN: 未知的文档类型 'prd-lite'，仅执行通用检查 / PASS`。三处（模板 / 常量 / checker）对 "lite 文档的类型名" 各执一词。后果：该 L2 短路白名单对 lite 文档**永不命中**（dead config），lite 文档反而走最严的 standard 检查。
- **建议**: 统一三处单一事实来源：建议 lite 模板 `doc_type` 改为 `-lite` 变体，并让 doc-review checker 注册 `-lite` 类型走放宽检查；或将常量改回基础类型并改用 `mode` 字段判定短路。涉模板 + 常量 + checker，需跨文件。

### [W-003] HIGH: KG-active 模式抬高 doc-review 门槛，lite 作者路径无法满足
- **category**: consistency
- **root_cause**: upstream-caused
- **描述**: KG-active（0.5.0 cutover）下 arch doc-review 跑「KG 覆盖检查」要求每个 PRD 功能有 KG 级实现/验证关系（实测 `FAIL: F 中 4 项缺少实现或验证: F-001..F-004`），dev-plan 跑实体级交叉引用解析（实测 `FAIL: 交叉引用目标 arch-lite#§2.M-002 在 KG 中未解析`）。但 agile-lite 的作者路径是「LLM 写纯 markdown + `cataforge docs index`」，并不把模块/功能/覆盖关系 ingest 成 KG 实体与 typed 关系 → 这些 KG 检查对 lite 文档必然失败。散文里的「对应功能: F-001」不会被当作覆盖关系。
- **建议**: lite 流程需补一步把模块/功能/覆盖关系 ingest 进 KG（或让 `docs index` 对 lite 文档自动建立 entity 级 xref）；否则 KG 覆盖类检查应在 lite 模式下降级为 WARN。涉 domain/kg + context skill，需跨包。

### [W-004] MEDIUM: 无"驱动/校验单个工作流阶段"的 CLI 入口
- **category**: completeness
- **root_cause**: self-caused
- **描述**: CLI 命令面有 setup/deploy/docs/skill/event/doctor 等，但**没有**"推进或校验某 phase 完成度"的入口；文档创建完全靠 LLM 按 context skill 写 markdown，无脚手架与产物存在性校验。后果实证：一个被指示"跑通工作流"的委派子代理把 `.cataforge/`+`.claude/` 全量部署完，就以为完成了——实际 `docs/` 为空、无 `EVENT-LOG.jsonl`、`PROJECT-STATE.md` 当前阶段仍是占位符 `{requirements|...}`。"框架已部署"与"工作流真被驱动"之间没有可机检的边界。
- **建议**: 提供 `cataforge phase status`（只读校验当前阶段应有产物是否齐备）类入口；本 skill 已在 observation-rubric「产物生成」维度部分覆盖，但应升为硬门槛。单点新增 CLI + 编排校验。

### [W-005] LOW: code-review 入口不支持 --help（与 doc-review 不一致）
- **category**: convention
- **root_cause**: self-caused
- **描述**: `cataforge skill run code-review -- --help` 报 `ERROR: 目标路径不存在: --help`（把 `--help` 当成扫描路径），而 doc-review 在坏参数时会打印 usage。两个同类 skill 的入口行为不一致，增加走查者试错成本。
- **建议**: code-review 入口识别 `--help`/无参时打印 usage。单点改动。

### [W-006] LOW: arch-lite 模板技术栈示例硬编码 "FastAPI"
- **category**: convention
- **root_cause**: self-caused
- **描述**: `context/templates/lite/arch-lite.md` 技术栈表示例写 `核心框架 | {如 FastAPI}`，在语言中立框架的模板里是轻微语言耦合气味（language-coupling 守卫不扫 templates 故未拦）。
- **建议**: 改为语言中立占位（如 `{如 Web 框架}`）。单点改动。

**正向观察（框架运转良好处）**：`cataforge setup` 全量部署成功且含新 skill；`cataforge docs index` 正确解析 deps 交叉引用；TDD 主干顺畅（纯逻辑表驱动 16 测试全绿）；`code-review scan` 端到端 PASS。

## 4. process findings（走查流程 / 本 skill 本身）

### [P-001] MEDIUM: 委派单个子代理"跑工作流"不可靠
- **category**: completeness
- **描述**: 把整条流程交给一个子代理，它可能只部署不驱动（实测首次委派即如此），且其返回报告不可机验。
- **建议**: walkthrough-protocol §3 增加硬规则——「每阶段结束即校验该阶段应有产物存在，缺失即判 blocked 并记录原始状态」；本轮已据此改由主线程亲跑并逐命令记录退出码。

### [P-002] MEDIUM: 缺 doc-review type 参数对照指引
- **category**: convention
- **描述**: 实测 doc-review 的 `<doc-type>` 必须传 front-matter `doc_type` 字面值（prd/arch/dev-plan）；传 `prd-lite` 会落到"未知类型仅通用检查"。SKILL/references 未点明，易踩坑。
- **建议**: walkthrough-protocol 补一行说明该参数取值来源。

### [P-003] LOW: 应提示走查者区分 KG 关系缺失 vs 自身漏写
- **category**: completeness
- **描述**: KG 覆盖类 FAIL（W-003）容易被走查者误判为"自己文档没写好"，而实为作者路径不建立 KG 关系。
- **建议**: observation-rubric「文档加载/KG」维度补一条判定指引（已部分覆盖，建议点名 KG 覆盖检查）。

### [P-004] LOW: code-review 探针跳过需与"0 findings"区分
- **category**: convention
- **描述**: 裸环境 `code-review scan` 因 jscpd 等未装跳过 3 个探针，仍报 RESULT: PASS / 0 findings，易被误读为"代码无任何问题"。
- **建议**: observation-rubric 增加"探针跳过(环境) ≠ 真实通过"的记录要求。

## 5. 产物清单 + 结论

**沙盒产物**（`walkthrough-sandbox/claude-code-agile-lite/`，gitignored）：
- `docs/prd-lite.md` / `docs/arch-lite.md` / `docs/dev-plan-lite.md` + `docs/.doc-index.json`
- `tempconv/{__init__,core,cli}.py` + `tests/{test_core,test_cli,test_errors}.py`
- pytest：`16 passed`

**自我校准**：W-001/002/003 经独立复核确为框架侧契约/配置不一致（命令、退出码、常量、模板均可复现对照），非走查者误用；W-004 由"委派 agent 部署却没驱动"的真实现象佐证。

**最值得优先的 3 项**：W-002（dead config，影响"lite 是否真轻量"的核心承诺）> W-001（lite 文档注定 FAIL，阻断 agile-lite 主干）> W-003（KG cutover 的系统性张力，牵动演进策略）。

**总体结论（三态判定）**：**approved_with_notes**。走查证明 agile-lite 主干**可端到端跑通**（部署/索引/TDD/代码评审均通），同时一次性暴露了 doc-review 在 agile-lite × KG-active 下对 lite 文档的系统性失败（3 个 HIGH）——这正是动态端到端走查相对静态 framework-review 的独特价值：这些 finding 只有真正跑一遍才会浮现。

## 6. 补充：并发第二次走查（独立 agent，`--project-dir` 模式）

本 skill 首次运行实际发生了两次并发走查：本报告主体来自主线程亲跑（`cd` 进沙盒），另有一个独立 agent 用 `cataforge --project-dir <sandbox> ...` 形式驱动同一沙盒。二者结论高度一致（均独立命中 W-001/002/003 同源问题），下列为第二次走查的**额外**发现。证据为该 agent 实跑记录，`R-S1` 建议在排期前做一次定点代码复核。

### [R-S1] HIGH: doctor `kg_ingestion_completeness` 门与 `kg import` 对"完整"的定义不一致，happy-path 无法清除
- **category**: consistency · **root_cause**: self-caused
- **描述**: `kg import` 自报 `verify ok=True missing=0`，但随后 `cataforge doctor` 仍 `FAIL: KG missing N entity_ids`（文档级 id），三条修复路径（`context ingest` / `kg repair` / `kg import`）均无法清除。疑因 `doctor/kg_ingestion.py` 把每篇 md 的 frontmatter `id` 当作必须存在的 `cf:entity_id`，而 importer 只为 item 级（F-/M-/T-/API- 等）发 `cf:entity_id`，从不为文档节点发文档级 id。
- **影响**: 任何 KG-active 项目把 `doctor` 接 CI 时，KG 完整性门可能在 happy-path 持续 FAIL 且无有效补救——比 doc-review 的 lite 失败更严重。
- **建议**: 对齐 importer 与 doctor 门对 `cf:entity_id` 的契约（importer 补发文档级 id，或 doctor 门改用文档节点 IRI 校验文档级、仅对 item 级查 `cf:entity_id`）。**建议先定点复核 `doctor/kg_ingestion.py` 的 entity_id 判定再排期。**

### [R-S2] MEDIUM→已修复: 全局 `--project-dir` 被 `kg init` / `docs index` 等忽略，写入宿主
- **category**: error-handling · **root_cause**: self-caused
- **描述**: `cataforge --project-dir <sandbox> docs index` / `kg init` 忽略该 flag、按 cwd 解析，向宿主根写 `docs/.doc-index.json` 与 `.cataforge/kg/`；`setup`/`deploy`/`doctor` 则正确 honor。
- **状态**: **已在本分支修复**（见 README §本分支已落地的修复）——新增 `helpers.root_relative_default`，`docs`(5) + `kg`(store/ingest/query 13) 子命令的本地 `--project-root`/`--db-path` 缺省时回退到全局 `--project-dir`，显式 local 仍优先；附 3 条回归测试。

### [R-S3] LOW: `cataforge setup` 在无 `.cataforge/` 的空目录中向上查找并附着父项目
- **category**: error-handling · **root_cause**: self-caused
- **描述**: 在未切 cwd 的沙盒跑 `setup` 时输出 `Project root: <宿主>`，对宿主执行（因平台已是 claude-code 而无 diff，侥幸无损）。`setup`（建新项目语义）应在 cwd 无 `.cataforge/` 时默认就地初始化或要求显式确认，而非静默附着父项目。

### [R-S4] LOW: Layer 1 skill-run hook 把"入参错误 exit 2"误记为"scripts unreachable"
- **category**: convention · **root_cause**: self-caused
- **描述**: `code-review -- --help`（`--help` 被当作不存在路径，exit 2）被 hook 记为 EVENT-LOG `exit=2 (unreachable scripts)`。应区分"脚本不可达 exit 2"与"业务入参错误 exit 2"。

### [P-S1] HIGH（process）: 沙盒 run-id `<platform>-<mode>` 非唯一，并发/重跑必撞目录
- **category**: structure
- **描述**: 两次并发走查共用 `walkthrough-sandbox/claude-code-agile-lite/`，互相写入对方产物，结果归因困难（本次正是据 observation-rubric §5 剥离归因）。
- **建议**: 已据此把"沙盒隔离 + 阶段产物存在性校验"列为本 skill 的改进项——`<run-id>` 应追加时间戳/短 hash，Step 1 增"目录非空即另起 run-id 或要求 `--clean`"护栏。这是"走查结果可信复现"的前置。

