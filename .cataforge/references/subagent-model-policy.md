# 子代理模型选型判据 — ad-hoc dispatch model policy

> 适用于派发**无 frontmatter 固定 tier** 的通用子代理（general-purpose / Explore / Plan / research 等）时的模型选择。CataForge 的 13 个框架 agent（architect / reviewer / implementer …）tier 由各自 AGENT.md `model_tier` 固定、deploy 解析为原生 `model:`，**不受本策略约束**；本策略只管调用方在派发时需**显式选择** `model` 的场景。

## 为什么必须显式指定

通用子代理定义里没有 `model:` 字段，按调度语义**继承主循环（会话）模型**。会话运行在 Opus 时，省略 `model` 会让检索、扫描、机械改写这类子代理**静默跑在 Opus 上**，成本翻数倍而无质量收益。派发时显式传 `model` 是把成本锁死的唯一手段。

## 判据

| 任务性质 | model | 说明 |
|---|---|---|
| 检索 / 广度扫描 / 机械改写 / 结构化抽取 / 单点定位 | `sonnet`（默认） | 派发时**显式** `model: "sonnet"`，不省略 |
| 跨文件根因定位 / 架构级权衡 / 对抗式验证 / 承重结论综合 | `opus` | 仅命中重推理判据才用 |
| 任意场景 | 禁 `haiku` | 与全局约束一致；`light` tier 解析为 haiku，同样不得用于 ad-hoc |

## 自检

派发通用子代理前问一句：这个任务是「找 / 读 / 改」还是「推理 / 权衡 / 验证」？前者 `sonnet`，后者才 `opus`。省略 `model` 等于默认继承 opus 会话——不要省略。
