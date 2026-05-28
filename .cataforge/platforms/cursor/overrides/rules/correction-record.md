# Correction Recording

本规则补偿 Cursor 缺失的 `detect_correction` PostToolUse hook。用户纠错信号不会被原生 hook 捕获，agent 必须主动落账。

## 触发条件

会话中出现以下任一信号即视为纠错事件：

- 用户否决 / 推翻 agent 上一步动作（"不对"、"应该是 X 而不是 Y"、"撤掉"、"重做"）
- 用户指出 agent 输出存在错误并要求修正
- 用户在 agent 已给出方案后变更约束或目标
- 用户提供 agent 本应推断到但遗漏的上下文 / 约束

## 必须执行

纠错事实发生**当轮**即记，不延后、不批量、不等用户提示：

```bash
cataforge correction record \
  --deviation <type> \
  --issue "<现象>" \
  --root-cause "<根因>" \
  --fix "<本次修复动作>" \
  --prevention "<规避建议>"
```

`<type>` 枚举与选型示例见 [docs/reference/corrections.md](../../../../../docs/reference/corrections.md)：

| 类型 | 何时选 |
|------|--------|
| `preference` | 团队风格 / 项目惯例与 baseline 不冲突，纯口味选择 |
| `self-caused` | agent 自身遗漏 / 误判，与 baseline 契约无关 |
| `external` | 外部环境 / 第三方工具 / 协作方约束驱动 |
| `framework-bug` | baseline 实现与文档承诺不符 |
| `upstream-gap` | baseline 在其设计场景下正确但未覆盖当前下游场景 |

## 边界

- 一次纠错对应**一条**记录；不要把多个独立纠错合并为一条
- 仅 `framework-bug` / `upstream-gap` 会进入 `cataforge feedback` 回流通道，其余止于本地 RETRO；选型时按事实归类，不要为了"回流"硬归到这两类
- 记录失败不应阻断当前任务（命令非 0 退出仅作 stderr 警告）
