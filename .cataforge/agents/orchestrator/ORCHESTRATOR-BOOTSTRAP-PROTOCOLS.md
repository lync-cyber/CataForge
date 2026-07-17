# Orchestrator Bootstrap Protocol

> 冷路径协议——每项目仅执行一次（{INSTRUCTION_FILE} 缺失时），按需加载，不进常驻
> [`ORCHESTRATOR-PROTOCOLS.md`](ORCHESTRATOR-PROTOCOLS.md)。

## Project Bootstrap
> 本协议是 from-scratch 项目 SDLC 初始化路径。框架包/脚手架的部署与**升级**不在此处——由 `framework-update apply` 的脊柱
> `cataforge bootstrap` / `cataforge upgrade apply` 幂等负责；本协议由 `framework-update apply` 在
> `{INSTRUCTION_FILE}` 缺失时委托进入，已存在时不重跑（走 Startup/Resume）。经 `framework-update apply`
> 进入时目标平台已由该脊柱确定，Step 7 直接取 framework.json `deployment.default_platform`，不重复选型/部署。

当项目从零开始 ({INSTRUCTION_FILE} 不存在) 时:
1. **收集项目基本信息** — 向用户确认: 项目名称、技术栈、命名规范、Commit格式、分支策略、人工审查检查点偏好（默认值见 COMMON-RULES §框架配置常量
   MANUAL_REVIEW_CHECKPOINTS）
2. **选择执行模式** — 通过 AskUserQuestion 单独提问，选项:
    - `standard`（默认/推荐）— 中大型正式交付项目
    - `agile-lite` — 轻量工具或小型 Web 项目
    - `agile-prototype` — 原型 / PoC / 单文件脚本
    完整差异矩阵见 COMMON-RULES §执行模式矩阵。选择结果写入 {INSTRUCTION_FILE} §项目信息.执行模式
3. **创建目录结构**: 根据执行模式:
    - `standard` / `agile-lite`: `mkdir -p docs/{prd,arch,dev-plan,ui-spec,test-report,deploy-spec,research,changelog,reviews/{doc,code,sprint,retro}}`
    - `agile-prototype`: `mkdir -p docs/{brief,research,reviews/{doc,code}}`
    - 存量项目带历史文档时，向用户确认归档方案：移入根级 `archive/`（docs 索引不扫描），或保留在 `docs/` 内并写
      `docs/.docignore`（一行一个 glob，`dir/` 匹配整个子树）——否则 `cataforge context validate` / doctor
      会对缺 front matter 的历史文件报 orphan FAIL
4. **git 基线与行尾归一化门** — 非 git 仓时先 `git init` 并落初始 commit（写入边界自检 / 崩溃恢复 / 回滚 / 增量审查协议均依赖 git
   基线）；`.gitattributes` 治理由 `cataforge setup` / `cataforge bootstrap` 自动执行，必要时可手动运行
   `cataforge setup gitattributes`。`cataforge doctor` 负责静态复核。
5. **创建 {INSTRUCTION_FILE}** — 按 ORCHESTRATOR-PROTOCOLS.md §{INSTRUCTION_FILE} Update Template
   生成，所有文档状态设为"未开始"，§项目信息.执行模式填入步骤 2 选定值；当前阶段按模式设置:
    - `standard` → `requirements`
    - `agile-lite` → `planning`（Phase 1+2 合并）
    - `agile-prototype` → `brief`（Phase 1~4 合并）
6. **框架版本无需手填** — 步骤 7 的 deploy 自动将已安装 cataforge 包版本盖入 {INSTRUCTION_FILE} `框架版本` 字段（无包元数据时由
   deploy 标注"未追踪"）
7. **选择目标平台** — 通过 AskUserQuestion 单独提问，选项:
    - `claude-code`（默认）— Anthropic Claude Code CLI / Desktop / Web
    - `cursor` — Cursor IDE
    - `codex` — OpenAI Codex CLI
    - `opencode` — OpenCode CLI
    确认后执行: `cataforge setup --platform {选定值} --deploy --language {Step 1 确认的语言}`（多语言逐个重复
    `--language`），该命令写入 `framework.json` 的 `deployment.default_platform`（并入 `deployment.targets`）并把
    语言固化到 `project.languages` —— 从零项目此时无 marker 文件可检测，以 Step 1 用户确认为准。经
    `framework-update apply` 委托进入（本步不重跑 setup）时，改用
    `cataforge config set project.languages {id,id,...}`（单参逗号分隔）固化；后续调整同此命令。`--deploy`
    链式生成对应平台的部署产物（不带该 flag 则需再运行 `cataforge deploy`）。若用户跳过选择则默认
    `claude-code`。随后运行 `cataforge config validate` 校验配置（旧布局提示时运行 `cataforge config migrate`
    迁移；单值查证用 `cataforge config explain <path>`）。
8. **填入 §执行环境 + 最小 permissions** — 按顺序运行两条命令:
   - `cataforge setup env-block`：将输出注入 {INSTRUCTION_FILE} §执行环境 节以替换占位符。退出码 2 表示未检测到已知技术栈，
     此时将该节内容置为 `- 无自动检测到的标准包管理器（请根据实际技术栈手动填写）`。
   - `cataforge setup permissions`：根据技术栈最小化平台配置中的 `permissions.allow`（Claude:
     `.claude/settings.json`，Cursor: `.cursor/hooks.json` + 权限策略），裁掉未使用的 Bash 白名单条目。
   本步骤的目的是让包管理器/安装命令/测试命令以项目指令形式固化到 {INSTRUCTION_FILE}，并收紧运行时权限以符合最小权限原则。
9. **初始化文档索引与知识图谱** —
   - `cataforge context ensure-store`（幂等，按 context.mode 水合图谱 store：graph 从最新 NQuads 快照恢复、
     markdown 跳过；store 已存在则原样保留）
   - `cataforge context index`（生成空的 `docs/.doc-index.json` 文档索引缓存，首个文档落盘后由生成定稿增量刷新）
   - 可选向用户提示 `cataforge viz framework` 渲染编排图，帮助快速建立流程心智模型
10. **进入初始阶段** — 先落初始阶段事件:
    `cataforge event log --event phase_start --phase {当前阶段} --detail "Bootstrap 完成，进入初始阶段"`
    （phase 取 {INSTRUCTION_FILE} §项目状态.当前阶段；三个 flag 均必填；`cataforge phase status --entry`
    的入口校验硬性期望该事件存在）。随后按 `framework.json#/workflow` 的 `execution_host` 分派
    （同 ORCHESTRATOR-PROTOCOLS.md §Phase Transition Protocol Step 4）进入 product-manager 角色:
    - `standard` → Phase 1 requirements
    - `agile-lite` → planning 阶段（按 ORCHESTRATOR-PROTOCOLS.md §Mode Routing Protocol 产出 prd-lite
      后链式进入 architect 产出 arch-lite）
    - `agile-prototype` → brief 阶段（产出单一 brief.md）
