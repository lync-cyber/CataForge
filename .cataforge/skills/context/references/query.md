# context · query(追溯查询)

把中文/英文追溯类问题翻译为只读查询,对项目知识图谱检索后用中文回答(如「哪些 Feature 没有测试覆盖」「谁依赖 M-002」「T-001 实现了哪个模块」)。只读,不修改图谱(写经 generate 分支);不做网络检索(由 research 负责)。

## 步骤
1. **取 schema card** — `cataforge kg schema-context`,拿实体类、追溯谓词及方向、标量 slot、示例查询(无需 store)
2. **翻译** — 据 card 与问题产出一条只读查询(SELECT/ASK/CONSTRUCT);类型用 `?x a cf:<Class>`,标识用 `cf:entity_id`/`cf:title`,追溯谓词按 card 标注方向遍历
3. **执行** — `cataforge kg query "<sparql>" --output table`(结果多时 `--output json`);写守卫与缺省 LIMIT 由命令内建
4. **失败重试** — 据 stderr 修正(类名/谓词拼写、方向、缺 `a cf:<Class>`),至多 3 次;仍失败说明卡点并附最后一版查询,不杜撰
5. **回答** — 中文陈述结论,附所用查询供核对;命中以 `entity_id + title` 呈现,空结果明确说「未命中」

## 前置
图谱已初始化并入图。store 不存在时如实告知用户先入图,不杜撰结果。

## Anti-Patterns
- 禁止: 跳过 schema card 凭记忆拼查询 — 实体类与谓词以 card 为准
- 禁止: 把空结果当失败反复重试 — 先判断是写错还是图中确实没有
- 禁止: 用本分支改图谱 — 即便问「把 T-001 标记为 done」也只回答现状并指向 generate 写路径
