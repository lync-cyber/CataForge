# 复杂度门禁（complexity_gate）语义细则

code-review Layer 1 检查 `code_review.complexity_gate` 的阈值模型、度量来源、代理度量算法与棘轮基线契约。实现：`cataforge.runtime.skill.builtins.code_review.checks.complexity`。

## 阈值声明（scope: project · complexity.yaml）

```yaml
schema_version: 2
scope: project
rule_type: complexity
thresholds:                      # 四指标必须全部显式声明（override 整文件替换）
  cyclomatic: { warn: 10, fail: 15 }
  cognitive: { warn: 15, fail: 25 }
  function_lines: { warn: 60, fail: 120 }
  nesting: { warn: 4, fail: 6 }
```

builtin 随包发运以上保守默认，**声明即激活**（区别于 arch 的 opt-in 模板）。校验：未知指标、缺失指标、非正整数、`warn > fail` 均加载即报错。

## 度量来源（优先级从高到低）

| 来源 | 覆盖指标 | 适用 |
|------|---------|------|
| radon `cc -j` | cyclomatic | `.py` |
| gocyclo | cyclomatic | `.go` |
| lizard `--csv` | cyclomatic（CCN） | 多语言兜底（py/go/js/ts/java/cs/rs） |
| pattern 代理度量 | 全部四指标 | 工具全缺时的兜底；cognitive / nesting / function_lines 恒由代理提供 |

每条 finding 标注 `度量来源`；工具可用性经 pipeline `tool_cache` 探测（与 scan probe 同 key，一次探测共享）。scan 模式的 radon / gocyclo / eslint probe 命令阈值同样取自 `complexity.yaml`（radon 用 `-n` 档位映射，gocyclo 用 `-over`，eslint 用 complexity 规则数值）。

## 代理度量算法（scope: language · complexity-{lang}.yaml）

1. **函数边界**：`function_patterns` 逐行匹配（捕获组 1 = 函数名）；跨度 = 定义行至首个缩进回落行（仅含闭合符号的同缩进行仍属函数体）。嵌套函数各自独立成条，同名函数按出现序加 `#N` 后缀入指纹。
2. **cyclomatic** = 1 + `branch_patterns` 命中数（逐行 findall 计数）。
3. **cognitive** = Σ 每次命中 (1 + 相对嵌套深度)——近似 Sonar 认知复杂度的"嵌套加权"，不实现其序列合并/跳转细则（代理度量取向：确定性优先于精确复刻）。
4. **nesting** = 函数体内最大相对缩进层级（缩进单位 = 函数体内最小正缩进差，tab 按 4 列展开）。
5. **function_lines** = 跨度行数（含定义行）。

各语言 branch 关键字清单以 `complexity-{lang}.yaml` 的 `branch_patterns` 为准（python 计 `if/elif/for/while/except/case` 行首语句；C 系语言另计 `case` 臂与 `&&`/`||`；rust 另计 `=>` match 臂）。

## 棘轮基线（.cataforge/baselines/complexity.json）

- **scan 刷新**：全量重算并覆写 `{"schema_version": 1, "metrics": {"<rel_path>::<func>": {...}}}`；同时把超 warn 函数输出为 informational finding（scan 不因复杂度 FAIL）。
- **review 只读 + 增量**：仅对 git diff（工作区 vs HEAD + untracked 全文件）涉及行覆盖的函数施判定；判据 `value > max(fail 阈值, 基线值)` → FAIL —— 触碰到的函数不得比基线更差，legacy 未触碰恒不阻塞；`warn < value ≤ 门禁` → WARN。git 信息不可用（非仓库/无 HEAD）时全部函数视为触碰。
- **防篡改**：framework-review B3-γ 对账 —— 基线变更（工作区或最近 commit）必须伴随 `docs/reviews/code/CODE-SCAN-*.md` 报告变更，否则 FAIL。
- **行级豁免**：`cataforge: allow(complexity_gate, reason="...")` 写在函数定义行，仅豁免该函数（语法见 [pragma-grammar.md](pragma-grammar.md)）。

## 已知盲区（Layer 2 职责）

- 代理度量的函数边界依赖缩进规整；单行函数、多行签名、宏生成代码会漏测或跨度失真
- 文件重命名 / 函数改名会使指纹脱离基线（按新函数施纯阈值判定——棘轮语义下的保守方向）
- 认知复杂度的序列合并、递归、跳转惩罚不在代理度量内 —— "该函数是否该拆"始终是 Layer 2 structure 维度判定
