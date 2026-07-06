# 走查流程自更新协议 (self-update)

本文件定义走查报告落盘后，process 类 findings 如何闭环回本 skill 资产，使同类摩擦不在后续每轮走查重复出现。framework 类 findings 不走本协议（只产报告，修复由 framework-review / 维护流程闭环）。

## 1. 宿主分流

- **框架仓本体**（仓库根 `pyproject.toml` 声明 `name = "cataforge"`，`.cataforge/` 即单一事实来源本体）→ 走 §2 自更新通道。
- **下游项目**（其余一切情形）→ 不修改 `.cataforge/` 任何文件——下游改动会在下次 framework-update apply 全量覆盖刷新时丢失。process findings 一律标 `resolution: proposed`，并在报告结论中提示经 framework-feedback 上游反馈打包（触发阈值见 RETRO_TRIGGER_UPSTREAM_GAP_DEFAULT）。

## 2. 自更新通道（仅框架仓本体）

1. **提案**：对每条 process finding 给出具体修改提案——目标文件（SKILL.md 或 `references/*.md`）+ 变更摘要 + 落点类型（澄清措辞 / 补步骤 / 增观察点 / 增探针 / 新增 reference 文档）。无法落成具体文本变更的（需人工权衡的方法论调整）直接标 `deferred`。
2. **确认**：把提案清单以选择题呈给用户（全部应用 / 逐条挑选 / 全部仅记录不写盘）。未经确认不写盘。
3. **应用**：确认后写盘，纪律：
   - 只改 `.cataforge/skills/framework-walkthrough/**`；其它任何路径（COMMON-RULES、其他 skill、CLI、协议文档）一律不动，相关改进作为 framework finding 留在报告。
   - 成块新知识（新平台差异、新观察维度、新探针族）优先插件式落 references/——新增独立文件或在既有文件追加小节，SKILL.md 主体只加一行链接；SKILL.md 主体仅在步骤本身错漏时修改。
   - 遵守项目指令文件 §Agent / Skill 撰写约定的三硬约束（最小可行修改 / 语言解耦 / 文档结构）。
   - 不自行 commit；改动留工作区，由标准 feature branch + PR 流程收口（含 run_local 静态守卫）。
4. **回填**：报告中每条 process finding 标 `resolution`：`applied`（已写盘）/ `proposed`（提案未被采纳，或下游场景）/ `deferred`（需人工权衡）。

## 3. 自更新边界（防自我放松）

自更新只允许**增补与澄清**，不允许收窄走查口径：

- 禁止删观察点、放宽 not-reached 判定、缩小探针清单以消掉反复出现的 process finding——摩擦反复出现说明它真实存在，收窄口径是掩盖而非修复。
- 观察面收窄（移除路径、降低严重度口径、缩小报告结构）必须作为 framework-review 议题由人工决策，不在本协议内完成。
- 单轮修改量以最小可行为限——一轮堆大量改动会让下轮走查无法归因改进有效性。下轮走查即是对本轮自更新的回归验证。
