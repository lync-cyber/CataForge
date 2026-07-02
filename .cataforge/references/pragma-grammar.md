# 文件级豁免注释统一语法（pragma grammar）

code-review Layer 1 所有机检的文件级豁免共用一种注释语法，由引擎统一解析（`cataforge.runtime.skill.builtins.code_review.engine.pragmas`）：

```text
cataforge: allow(<check-id>, reason="<非空理由>")
```

## 规则

1. `<check-id>` 取 `CHECKS_MANIFEST` 中的检查 id，全名（`code_review.ui_fidelity`）或去命名空间的短名（`ui_fidelity`）均可。
2. 注释风格不限（`//`、`#`、`/* */`、`--` 等），仅豁免所指检查，不影响其他检查。生效范围随消费方（见下表）：**文件级**消费方任意行出现即对整个文件生效；**行级**消费方要求 pragma 位于违规行同行，仅豁免该行。
3. `reason` 必填：缺失时豁免仍生效（渐进采用），但消费该豁免的检查会产出一条 WARN finding（`缺 reason`），保证豁免蔓延始终可见。理由应指向可追溯的依据（backlog ID、任务卡、设计决定）。
4. 一行可写多个 pragma；同一文件对同一 check 的重复 pragma 以首个为准。

## 当前消费方

| check-id | 生效范围 | 豁免效果 |
|----------|---------|---------|
| `wiring_empty_handler` | 文件级 | 跳过该文件的空 handler 扫描（分阶段实现配任务卡 `wiring_placeholder: true`） |
| `ui_fidelity` | 文件级 | 跳过该文件的死 token / 未加载字体 / 幽灵类扫描 |
| `arch_guard` | 行级 | 豁免同一行 import 的分层方向违规判定 |
| `complexity_gate` | 行级（函数定义行） | 豁免该函数的复杂度门禁判定 |
| `config_dead_key` | 文件级（声明文件） | 跳过该文件声明的 config key 的死键判定（外部基础设施消费场景） |

scan 的 `pragma_inventory` 探针会枚举全部豁免（check / reason / git blame 引入天数）并把非本语法的 `cataforge` 标记残留报为 unknown-pragma——豁免只增不减时在 CODE-SCAN 报告可见。

## 示例

```tsx
// cataforge: allow(wiring_empty_handler, reason="M2 分阶段接线，backlog B-12")
```

```css
/* cataforge: allow(ui_fidelity, reason="token 由运行时主题注入，静态扫描不可见") */
```

```python
import myapp.infra.db  # cataforge: allow(arch_guard, reason="遗留直连，迁移卡 B-31")
```

任务卡级豁免（如 `wiring_placeholder: true`）与本语法互补：任务卡字段面向 Layer 2 / 评审流程，本语法面向 Layer 1 机检的单文件粒度。
