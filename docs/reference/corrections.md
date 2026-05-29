# CORRECTIONS-LOG — Deviation 类型语义

> `cataforge correction record --deviation <type>` 接受的 5 种偏差类型。**只有 `upstream-gap` 一种会进入 `cataforge feedback correction-export` 的回流 bundle**；其它 4 类止步于下游本地 RETRO。下游 corrections 全标 preference / self-caused 时回流通道会一直空转。

## 当前枚举

由 `cataforge.core.corrections.VALID_DEVIATIONS` 定义：

| 类型 | 回流上游？ | 触发场景 |
|------|----------|---------|
| `preference` | 否 | 下游团队风格 / 项目惯例与 baseline 不冲突，纯口味选择 |
| `self-caused` | 否 | 下游执行 baseline 时自身犯错或绕过，与契约无关 |
| `external` | 否 | 外部环境 / 第三方工具 / 协作方约束驱动 |
| `framework-bug` | 走 `feedback bug` 通道 | baseline 实现与文档承诺不符，是确切缺陷 |
| `upstream-gap` | **是**（`feedback correction-export`） | baseline 在其设计场景下正确但**未覆盖下游场景** |

`framework-bug` 与 `upstream-gap` 的核心区别：**前者是 baseline 错了，后者是 baseline 没考虑到**。两者都该回流但走不同通道。

## 选型示例

### preference

- baseline 推荐 4 空格缩进，团队约定 2 空格
- baseline 默认 sprint 长度 2 周，项目改 1 周
- baseline `dev-plan-{project}.md` 命名，团队改用 `plan.md`

### self-caused

- orchestrator 未读 ARCH 直接拆任务，AC 与契约不匹配
- implementer 跳过 lint 直接 commit，下次审查被 reject
- tech-lead 漏算依赖路径，sprint 中段出现循环依赖

`RETRO_TRIGGER_SELF_CAUSED` 阈值用本类计数（累积触发 RETRO 兜底）。

### external

- 客户公司禁用 Docker，必须切到 podman
- 部署平台不支持 baseline 推荐的依赖版本
- 协作方 API gateway 限流，测试需重写为 batched 模式

### framework-bug

baseline 实现 ≠ 文档承诺。回流通道 `cataforge feedback bug --gh`。

- `cataforge X --out Y.md` 落盘文件不符合自身 doctor 索引器的强制要求
- `cataforge issue triage` 默认 label 用 AND 语义但文档说是 OR
- skill 输出契约与 reflector / doctor 索引器枚举不一致

### upstream-gap

baseline 在其设计场景下正确，但下游场景在意图之外。判定模式：

- **枚举值缺失**：上游 schema / status / 类型不覆盖下游需要表达的状态（如 EVENT-LOG 缺某类事件枚举）
- **协议假设不成立**：baseline 假设的协作模式与项目实际不符（如假设单一上游 fork，项目有多 baseline 来源）
- **边界外契约冲突**：契约与实际行为冲突，且冲突输入来自 baseline 边界外
- **fork / 定制场景不适用**：baseline 在 fork 项目环境下行为偏差

回流通道 `cataforge feedback correction-export` 仅打包本类记录；`RETRO_TRIGGER_UPSTREAM_GAP_DEFAULT`（默认 3）累积时提示开 issue。

## 不在枚举内的常见误标

下游 RETRO 中曾出现但**当前 CLI 不接受**的类型，遇到时按下表二选一重新归类：

| 误标 | 应归入 | 判据 |
|------|-------|------|
| `protocol-gap` | `self-caused` 或 `upstream-gap` | 如果下游漏读 / 误读了上游协议 → self-caused；如果协议本身没覆盖下游场景 → upstream-gap |
| `technical-constraint` | `external` | 含义重叠 — 外部环境驱动 |
| `framework-debt` | `framework-bug` 或 `upstream-gap` | 如果是已知未修缺陷 → framework-bug；如果是设计缺口 → upstream-gap |

`cataforge correction record --deviation <X>` 用 click.Choice 强校验，错值即拒，从源头杜绝自由文本类型。

## CLI 速查

```
cataforge correction record \
  --trigger interrupt-override \
  --agent orchestrator \
  --phase architecture \
  --question "..." \
  --baseline "..." \
  --actual "..." \
  --deviation upstream-gap
```

`--trigger` 三态：`option-override` / `interrupt-override` / `review-flag`。
`--deviation` 缺省 `self-caused`，保持 RETRO 计数兜底；显式标 `upstream-gap` 才会进回流 bundle。

## 引用

- 实现：`src/cataforge/interface/cli/correction_cmd.py` / `src/cataforge/core/corrections.py`
- 回流：`cataforge feedback correction-export` —— 见 `src/cataforge/core/feedback.py` `UPSTREAM_GAP` 常量
- 报告：`docs/reviews/CORRECTIONS-LOG.md`（项目本地，每次 `record` 追加）
