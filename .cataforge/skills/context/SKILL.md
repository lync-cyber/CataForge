---
name: context
description: "统一上下文 I/O — 按需读取章节/实体、查询追溯关系、生成与写入、门禁校验。文档生命周期的单一入口；后端(知识图谱/文件)由框架按配置方案透明路由,调用方只表达意图。按操作分支见 references/。"
argument-hint: "<操作: navigate|generate|review|consistency|query>"
suggested-tools: shell_exec, file_read, file_glob, file_grep
depends: []
disable-model-invocation: false
user-invocable: true
---

# 统一上下文 I/O (context)

文档生命周期的单一能力入口。读取、关系查询、生成/写入、校验都经 `cataforge context` / `cataforge docs` 表达**意图**;由哪个后端服务、用何种保真度,由框架按项目配置的上下文方案路由,调用方无需感知。后端能力**非对称**:读取/生成/校验按方案路由且在后端不可达时降级;关系追溯(query 分支)是图原生能力,需图后端就绪(无对等文件回退)。

## 能力边界
- 能做: 按需加载章节/实体、依赖与追溯查询、文档生成与写入、单文档与跨文档门禁校验
- 不做: 内容决策(由调用 Agent 负责)、代码审查(由 code-review 负责)、框架元资产审查(由 framework-review 负责)

## 输入规范
- 操作分支: `navigate` | `generate` | `review` | `consistency` | `query`
- 引用: `doc_id#§N[.item]`(如 `prd#§2.F-001`、`arch#§1`)
- 各分支的参数与命令见对应 reference 文件

## 输出规范
- 读取: 目标章节/实体内容(markdown 形式,后端无关)
- 查询: 依赖/追溯结果
- 生成/写入: authoring 落图 + 定稿导出路径
- 校验: 审查/一致性报告 + 三态结论

## 操作指令
按意图选分支,详见 reference:

1. **navigate** — 按需读取章节/实体、依赖展开、token 预算。见 [references/navigate.md](references/navigate.md)
2. **generate** — 取模板、authoring 落图、定稿导出、拆分。见 [references/generate.md](references/generate.md)
3. **review** — 单文档门禁(脚本检查 + 语义审查)。见 [references/review.md](references/review.md)
4. **consistency** — 跨文档一致性(覆盖矩阵、契约对齐)。见 [references/consistency.md](references/consistency.md)
5. **query** — 自然语言追溯查询。见 [references/query.md](references/query.md)

## Anti-Patterns
- 禁止: 一次性 Read 超过 200 行的整篇文档 — 按章节/条目加载是核心价值,全文 Read 吃掉数千 token 还引入无关噪声
- 禁止: 在调用面判断"该走哪个后端" — 后端选择由框架路由,prompt 里复述分发条件会随实现漂移
- 禁止: 跳过 generate 的定稿步骤直接退出 — 定稿负责持久化与事件写入,跳过会让后续读取/校验找不到新内容
- 避免: 同一会话重复加载同一章节 — 内容已在上下文,重复加载浪费 turn 和 token
