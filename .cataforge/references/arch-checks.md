# 架构分层守护（arch_guard）语义细则

code-review Layer 1 检查 `code_review.arch_guard` 的判定语义、各语言 import 形态与已知盲区。实现：`cataforge.runtime.skill.builtins.code_review.checks.arch_guard`。

## 模型声明（scope: project · arch.yaml）

```yaml
schema_version: 2
scope: project
rule_type: arch
enforce: fail            # fail = 违规即门禁；warn = 影子运行（违规仅 WARN）
layers:                  # 声明顺序 = 归层匹配优先级
  - name: interface
    paths: ["src/myapp/api/**"]      # 项目根相对的文件 glob（源文件归层 + 相对导入目标归层）
    modules: ["myapp.api"]           # import 语句里的模块前缀（绝对导入目标归层）
rules:                   # 方向矩阵：每个已声明层必须显式列出可依赖层；自身恒可，不必列出
  interface: []
```

- 未声明模型（无 arch.yaml 或全部注释）→ 检查静默不激活，scan 输出一条 INFO。包内 `rules/arch.yaml` 即注释模板。
- 结构校验（loader `extra_validator`）：未知层名、矩阵引用未声明层、缺失某层的方向声明、`enforce` 非法值均在加载时报错；framework-review B3-β 对项目 YAML 呈现为 audit finding。

## 判定语义

1. **源文件归层**：文件的项目根相对路径匹配层 `paths` glob（`**` 跨 `/`，`*`/`?` 不跨；尾部 `/**` 也匹配目录本身）。未归层文件不受检。
2. **依赖边提取**：按扩展名选 `arch-{lang}.yaml` 的 `import_patterns`（捕获组 1 = 被导入模块）。
3. **目标归层**：相对说明符（`../infra/db`、`.infra`、`..infra.db`）对源文件目录解析后匹配 `paths`；绝对说明符按 `modules` 前缀匹配（分隔符 `.` / `/` / `::` 边界对齐，前缀相等或前缀+分隔符）。两者都不命中（第三方 / 标准库 / 未分层代码）→ 忽略。
4. **矩阵判定**：同层恒放行；目标层在 `rules.<源层>` 列表内放行；否则按 `enforce` 出 FAIL/WARN finding。
5. **行级豁免**：`cataforge: allow(arch_guard, reason="...")` 写在违规 import 同行，仅豁免该行（语法见 [pragma-grammar.md](pragma-grammar.md)）。

## 各语言 import 形态覆盖

| 语言 | 覆盖形态 | 目标归层方式 |
|------|---------|-------------|
| python | `import a.b` / `from a.b import x` / `from .rel import x` / `from . import x` | 绝对 → modules；点前缀 → 路径解析 |
| js-ts | `import … from '…'` / `import '…'` / `export … from '…'` / `require('…')` / `import('…')`（字面量） | `./`、`../` → 路径解析；bare / alias → modules |
| go | 单条 import / import 块内条目 | modules（模块路径前缀，如 `example.com/app/infra`） |
| java | `import [static] a.b.C` | modules（包前缀） |
| csharp | `[global] using [static] A.B;` / using 别名 | modules（命名空间前缀） |
| rust | `[pub] use crate::a::b` | modules（`::` 分隔前缀，如 `crate::infra`） |

## 已知盲区（Layer 2 职责）

以下形态正则提取不到或不可判定，**显式声明为 Layer 2 语义审查（structure 维度）职责**，不追求静态完备：

- 动态 import 的计算说明符（变量 / 字符串拼接模块名、python `importlib.import_module(expr)`、反射加载）
- re-export 链穿透（A re-export B，C import A 只记 C→A 一跳，不展开到 C→B）
- js-ts tsconfig `paths` 别名解析（需项目在层 `modules` 里显式声明别名前缀，如 `@/infra`）
- python `import a, b` 多目标仅取首个；`__init__.py` 聚合导出的实际来源
- go build tags / cgo 条件编译分支；csharp `extern alias`
- 无 import 信号的语义越层（职责错置、接口层内嵌业务规则）——始终是 Layer 2 判定
