# 语言上下文 SSOT

CataForge 用一个**单一来源**描述项目用到的编程语言：`framework.json` 的 `project.languages`。语言相关的规则选择、agent 语言细则注入、探测兜底都从这里取值，集合永不在多处各写一份而漂移。

## canonical id

每种语言有一个规范 id，与 wiring / e2e 规则 YAML 的 `language:` 字段一致：

| id | 说明 | 探测 marker（项目根） | 扩展名 |
|----|------|----------------------|--------|
| `python` | Python | `pyproject.toml` / `setup.py` / `setup.cfg` / `requirements.txt` / `Pipfile` | `.py` `.pyi` |
| `js-ts` | JavaScript / TypeScript | `package.json` / `tsconfig.json` / `deno.json` | `.js` `.ts` `.jsx` `.tsx` `.mjs` `.cjs` |
| `go` | Go | `go.mod` | `.go` |
| `rust` | Rust | `Cargo.toml` | `.rs` |
| `csharp` | C# | `*.csproj` / `*.sln` | `.cs` |
| `java` | Java | `pom.xml` / `build.gradle` / `build.gradle.kts` | `.java` |

注册表本体：[`cataforge.core.languages.LANGUAGES`](../../src/cataforge/core/languages.py)。新增语言**只改这一处**。

> 内置 wiring / e2e 规则当前覆盖 `python` 与 `js-ts`；其余注册语言可正常声明并参与下文的 agent 语言细则注入，但若要 Layer 1 wiring / e2e 扫描，需在覆盖层自带对应规则 YAML（见 [`overrides.md`](overrides.md) §skill 级 rules YAML）。

## 声明 vs 探测

解析顺序（[`active_languages`](../../src/cataforge/core/languages.py)）：

1. `project.languages` 非空 → 以它为准，做 alias 归一化（`typescript`→`js-ts`、`golang`→`go`、`py`→`python` 等）。
2. 为空 → 按 marker 文件自动探测项目根。

未知 id 原样保留（小写），不静默丢弃——允许声明注册表尚未覆盖的语言。

## 声明语言

```bash
cataforge setup --language typescript --language go   # 写入 project.languages = ["js-ts","go"]
```

synonyms 自动归一化为 canonical id。不带 `--language` 时 setup 会提示当前探测到的语言，并说明读取时按 marker 兜底。`project.languages` 是 `upgrade apply` 的 preserve 字段（见 [`configuration.md`](./configuration.md)），升级不会重置。

## agent / skill 语言细则

agent / skill prompt 主体保持语言无关（`check_no_language_coupling` 守卫强制 `AGENT.md` / `SKILL.md` 主体不含语言业务关键字）。语言特定内容放进 owning skill 的**参考文件** `.cataforge/skills/<id>/references/lang-<lang>.md`（在守卫扫描范围之外）。

部署时 `deploy_skills` 整目录拷贝，`references/` 子目录随 skill 自包含落地到 `.claude/skills/<id>/references/` —— 主对话直用 skill 与子代理执行 skill 走同一份。各 owning SKILL.md 指示按 `project.languages` 只载入 active 语言对应的 `references/lang-<lang>.md`（逐个 Read；6 种语言全落地，按需读取）。

归属映射：

| 语言细则 | owning skill |
|---------|-------------|
| 技术选型 | `arc-design` |
| 代码评审 | `code-review` |
| 测试编写 | `testing` |
| 实现编码 | `tdd-engine` |
| 调试诊断 | `debug` |
| 构建部署 | `deploy-config` |

TDD 子代理（test-writer / implementer）无 owning skill，由 `tdd-engine` 在组装 RED / GREEN 派发 prompt 时注入对应 `references/lang-<lang>.md` 路径。

## 自定义 rule_type

skill 规则加载器的 rule_type 是可注册的（`register_rule_type`），内置 `wiring` / `e2e` / `doc_terms`。新规则族（含项目 / 插件覆盖）调用 `register_rule_type(name, list_pattern_keys=..., single_pattern_keys=...)` 即被 `validate_yaml_text` 接受，无需改加载器本体。

## 防漂移契约

`tests/core/test_languages.py` 的 parity 测试断言：**每个内置 wiring / e2e 规则 YAML 的 `language` id 与 `extensions` 都必须在注册表中存在且一致**。新增一条 `wiring-<lang>.yaml` 而忘了登记语言，测试立即失败，逼着回到 `LANGUAGES` 补齐——这是"避免漂移"的硬约束，而非约定。
