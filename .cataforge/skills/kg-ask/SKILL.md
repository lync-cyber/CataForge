---
name: kg-ask
description: "知识图谱自然语言查询 — 把中文/英文问题翻译为只读 SPARQL，针对项目知识图谱（需求/模块/任务/测试的追溯关系）检索并用自然语言回答。当用户想问『哪些 Feature 没有测试覆盖』『任务 T-001 实现了哪个模块』『F-001 的验收标准有哪些』『谁依赖 M-002』等追溯类问题时使用此 skill。本 skill 只读，不修改图谱（写操作由 kg add/update/delete 负责），不做网络检索（由 research 负责）。"
argument-hint: "<自然语言问题，如：哪些 Feature 没有测试覆盖>"
suggested-tools: Bash, Read
depends: []
disable-model-invocation: false
user-invocable: true
---

# kg-ask · 知识图谱自然语言查询

把用户的自然语言问题翻译为只读 SPARQL，对项目知识图谱检索后用中文回答。翻译由本 agent 据 schema card 完成；执行、写守卫、LIMIT 注入全部复用 `cataforge kg query`。

## 能力边界

- 只读检索：仅产出 SELECT / ASK / CONSTRUCT。写操作（新增/更新/删除实体或关系）不在本 skill 范围，转 `cataforge kg add/update/delete`。
- 仅查本项目知识图谱：回答的依据限于图谱中已 ingest 的实体与追溯边，不引入外部知识；需要外部资料时转 research skill。
- 前置条件：图谱已初始化并 ingest（`cataforge kg init` + `cataforge kg import`）。store 不存在时如实告知用户先 ingest，不杜撰结果。

## 操作指令

1. **取 schema card** — 运行 `cataforge kg schema-context`，拿到实体类、追溯谓词、标量 slot、示例查询。card 是静态的，无需 store 即可获取。
2. **翻译为 SPARQL** — 据 card 与用户问题产出一条只读查询：用 `PREFIX cf: <…>`（取自 card 首行）、`?x a cf:<Class>` 定类型、`cf:entity_id` / `cf:title` 取标识、追溯谓词按 card 标注的方向遍历。实体计数/存在性用 ASK，列举用 SELECT。
3. **执行** — 运行 `cataforge kg query "<sparql>" --output table`（结果多时加 `--output json` 便于解析）。写守卫与缺省 LIMIT 注入由该命令内建强制，无需在本 skill 重复实现。
4. **失败重试** — 解析错误、空结果或超时时，据 stderr 修正查询（常见：类名/谓词拼写、方向写反、缺 `a cf:<Class>` 约束）后重试，至多 3 次。仍失败则向用户说明卡点并附最后一版 SPARQL，不杜撰答案。
5. **回答** — 用中文陈述结论，附所用 SPARQL 供用户核对；命中实体以 `entity_id + title` 呈现，空结果明确说明『未命中』而非编造。

## Anti-Patterns

- 禁止：跳过 schema card 凭记忆拼 SPARQL — 实体类与谓词以 card 为准，否则易把 `cf:implements` 与 `cf:satisfies` 用反（Module 用 implements、Page 用 satisfies）。
- 禁止：把空结果当作失败反复重试 — 先判断是『查询写错』还是『图谱中确实没有』，后者直接如实回答未命中。
- 禁止：向用户暴露原始 SPARQL 错误堆栈而不解释 — 把 stderr 转译为用户能理解的卡点描述。
- 禁止：用本 skill 改图谱 — 即便用户问『把 T-001 标记为 done』，也只回答现状并指向 `cataforge kg update`。
