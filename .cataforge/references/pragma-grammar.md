# 文件级豁免注释统一语法（pragma grammar）

code-review Layer 1 所有机检的文件级豁免共用一种注释语法，由引擎统一解析（`cataforge.runtime.skill.builtins.code_review.engine.pragmas`）：

```text
cataforge: allow(<check-id>, reason="<非空理由>")
```

## 规则

1. `<check-id>` 取 `CHECKS_MANIFEST` 中的检查 id，全名（`code_review.ui_fidelity`）或去命名空间的短名（`ui_fidelity`）均可。
2. 注释风格不限（`//`、`#`、`/* */`、`--` 等），任意行出现即对**整个文件**生效，仅豁免所指检查，不影响其他检查。
3. `reason` 必填：缺失时豁免仍生效（渐进采用），但消费该豁免的检查会产出一条 WARN finding（`缺 reason`），保证豁免蔓延始终可见。理由应指向可追溯的依据（backlog ID、任务卡、设计决定）。
4. 一行可写多个 pragma；同一文件对同一 check 的重复 pragma 以首个为准。

## 当前消费方

| check-id | 豁免效果 |
|----------|---------|
| `wiring_empty_handler` | 跳过该文件的空 handler 扫描（分阶段实现配任务卡 `wiring_placeholder: true`） |
| `ui_fidelity` | 跳过该文件的死 token / 未加载字体 / 幽灵类扫描 |

## 示例

```tsx
// cataforge: allow(wiring_empty_handler, reason="M2 分阶段接线，backlog B-12")
```

```css
/* cataforge: allow(ui_fidelity, reason="token 由运行时主题注入，静态扫描不可见") */
```

任务卡级豁免（如 `wiring_placeholder: true`）与本语法互补：任务卡字段面向 Layer 2 / 评审流程，本语法面向 Layer 1 机检的单文件粒度。
