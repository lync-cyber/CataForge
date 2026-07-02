# 覆盖层 — 定制 agent / skill 而不被升级冲掉

框架发货的 agent / skill 放在 `.cataforge/agents/`、`.cataforge/skills/`，这些目录由 `cataforge upgrade apply` 全量刷新。要长期定制又不被升级覆盖，把改动放进**覆盖层**：

```
.cataforge/overrides/user/{agents,skills}/      # 个人，最高优先级
.cataforge/overrides/project/{agents,skills}/   # 团队共享
```

覆盖层不在 scaffold manifest 里，`upgrade apply` 永不触碰它们。两层默认都随仓库提交（团队共享 project 层、个人偏好走 user 层）。

> 覆盖层目录默认为空或尚未存在——不随 scaffold 分发、不进 manifest。用下方 `cataforge override eject` 从发货层导出第一个定制起点即自动创建对应层目录。

## 优先级

同一个 asset（agent / skill 子目录）跨层解析，**高层胜出**：

```
overrides/user/   >   overrides/project/   >   .cataforge/（发货层）   >   包内 builtin
```

skill 运行期（`cataforge skill run` / `skill list`）和 deploy（落地到 IDE）都按这个顺序解析。

## 两种粒度

### 1. 整文件覆盖

在覆盖层放一个完整的 `AGENT.md` / `SKILL.md`，整体替换基线文件。改 frontmatter（agent 的 `tools` / `model_tier`、skill 的 `description` 等）必须走整文件覆盖——frontmatter 在第一个 `##` 之前，section patch 不碰它。

```
.cataforge/overrides/project/agents/architect/AGENT.md   # 替换整个 architect prompt
```

### 2. section 补丁（覆盖已有 section + 新增 section）

在覆盖层放 `<name>.patch.md`，它的每个 `##` 标题：

- **标题与基线某 section 同名 → 覆盖**该 section 的正文；
- **标题是新的 → 追加**到基线 section 之后。

只有 `##`（H2）划分 section；`###` 及更深的标题属于所在 H2 正文，随其一起被替换。

```markdown
<!-- .cataforge/overrides/project/agents/architect/AGENT.patch.md -->
## Execution Rules
- 改写后的执行规则（覆盖基线同名 section）

## 团队专属约定
- 新增 section，追加到末尾
```

补丁按层叠加：project 层 patch 先作用于发货层，user 层 patch / 整文件再叠加在其上。

> sibling 文件（`ORCHESTRATOR-PROTOCOLS.md` 等）同样支持：覆盖层放同名文件整体替换，放新文件则新增。`<name>.patch.md` 对任意 markdown sibling 都生效。

## CLI

```bash
# 列出每个 agent/skill 由哪些层定义
cataforge override list

# 从发货层导出一个起点（默认 project 层、整文件）
cataforge override eject agents architect

# 导出到 user 层、生成 section 补丁骨架，并把某 section 的当前正文塞进去
cataforge override eject agents architect --layer user --patch --section "Execution Rules"
```

`eject` 写好起点后，编辑它再 `cataforge deploy` 即落地。已存在的覆盖文件需 `--force` 才覆写。

## skill 级 rules YAML

`skills/<id>/rules/*.yaml`（wiring / e2e / arch / complexity / config_keys / api_surface 等全部 rule_type）也走覆盖层：

```
.cataforge/overrides/{project,user}/skills/<id>/rules/<rule_type>[-<lang>].yaml
```

运行期 `discover_rules` 按同样的高层胜出顺序、以 `(rule_type, language)` 为键整文件替换合并，覆盖 YAML 改完即被 Layer 1 采纳。schema v2：必填 `schema_version: 2` / `rule_type` / `scope: language|project`（`scope: language` 必填 `language`/`extensions`；`scope: project` 供语言无关的项目级模型，不写这两键）；未知顶层键报错；全注释 YAML 视为未声明（模板语义）。framework-review B3-β 对项目层 YAML 自动做 schema 校验。语义细则见 [`wiring-checks.md`](../../.cataforge/references/wiring-checks.md) / [`arch-checks.md`](../../.cataforge/references/arch-checks.md) / [`complexity-checks.md`](../../.cataforge/references/complexity-checks.md)。

## 项目 override 脚本的 CLI 契约

review-class skill（`code-review` / `doc-review` / `sprint-review`）在项目层放自己的 Layer 1 脚本（`.cataforge/skills/<id>/scripts/` + SKILL.md frontmatter 声明）时，`cataforge skill run <id> -- <args>` 会把 `--` 之后的参数原样转发给该脚本。脚本必须实现与 builtin 相同的 CLI 面，否则上层 SKILL.md 散文（以及 orchestrator / tdd-engine 的调用点）会以不匹配的参数调起它。

以 `code-review` 为例（builtin `code_check.py` 的契约）：

**子命令**

```
review <path> [--fix] [--focus <category[,...]>] [--format text|json]
scan   <path> [--focus <category[,...]>] [--format text|json]
```

**退出码**（COMMON-RULES §Layer 1 调用协议四态的脚本侧三态）

| 码 | 语义 |
| --- | ------ |
| `0` | PASS — 无 gating finding |
| `1` | 有 gating finding（needs_revision 输入） |
| `2` | 用法错误 / 目标路径缺失 —— 未知参数与非法 `--focus` 值必须落这里，不得静默忽略 |

**`--format json` 输出 schema**（Layer 2 与报告聚合的机读输入）

```json
{
  "mode": "review|scan",
  "target": "<path>",
  "checks_run": ["<check_id>", "..."],
  "findings": [
    {
      "check_id": "<namespace.check>",
      "severity": "fail|warn|info",
      "category": "<COMMON-RULES 统一分类>",
      "file": "<path 或 null>",
      "line": "<int 或 null>",
      "detail": "<人读描述>"
    }
  ],
  "summary": { "fail": 0, "warn": 0, "info": 0 },
  "result": "PASS|FAIL"
}
```

`severity: fail` 的 finding 存在 ⇔ exit 1 ⇔ `result: FAIL`；`warn` / `info` 不影响退出码。仅覆写 SKILL.md 散文而不带 `scripts/` 时无需实现本契约——`SkillLoader` 自动回落到内置脚本。

## 与升级的关系

- `.cataforge/agents` / `.cataforge/skills`：发货层，`upgrade apply` 全量刷新；手改过的文件会被保留并落 `.cataforge-new` 旁路文件（见 [`../guide/upgrade.md`](../guide/upgrade.md)），但**正确做法是把定制放进覆盖层**而不是直接改发货层。
- `.cataforge/overrides/`：升级免疫，定制的归宿。
