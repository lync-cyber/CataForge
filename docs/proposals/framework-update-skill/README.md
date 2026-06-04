# 整合：`/bootstrap` command 与 `self-update` skill 合并为 `framework-update` skill

> 状态：已实施（refactor/framework-update-skill）
> 关联审查：[`docs/reviews/framework/FRAMEWORK-REVIEW-all-20260604-r1.md`](../../reviews/framework/FRAMEWORK-REVIEW-all-20260604-r1.md) R-001

## 1. 问题

`.cataforge/commands/bootstrap.md`（`/bootstrap` command）与 `.cataforge/skills/self-update`（`/self-update` skill）都是 `cataforge bootstrap` CLI 的薄包装层，对同一条脊柱各写了一遍调用协议（dry-run → 确认 → apply → 降级分支），双轨维护必然漂移。两者真正互补的是脊柱**前后的侧翼**，拼起来正好是一条完整的「框架生命周期」链路。

## 2. 现状职责映射

`cataforge bootstrap`（CLI，幂等、自决每步 skip/run）是唯一脊柱：

```
┌──────────────────── cataforge bootstrap（脊柱，幂等）────────────────────┐
│  setup（拷 scaffold） → upgrade（刷 scaffold） → deploy（IDE 产物） → doctor │
└──────────────────────────────────────────────────────────────────────────┘
        ▲ 前置侧翼                                          后置侧翼 ▼

self-update apply：
   前  + pip/uv 包升级（脊柱只把 scaffold 对齐到"已安装包"，不升级包本身）
   后  + upgrade.state 写入 + {INSTRUCTION_FILE} 框架版本同步 + claude-md hygiene

bootstrap.md：
   后  + 项目 init / resume（委托 ORCHESTRATOR-PROTOCOLS §Project Bootstrap）
   后  + env-block / permissions 装配 + 交接 start-orchestrator
```

- **脊柱重叠**：bootstrap.md Step 1 ≡ self-update apply Step 4，都是 `cataforge bootstrap`。
- **侧翼互补**：包升级（前）、版本簿记（后）、项目 init/resume（后）彼此独立，可线性拼接。
- **包升级是 self-update 独有**：脊柱把 scaffold 对齐到「已安装包版本」，不执行 `pip install -U` / `uv tool upgrade`。
- **init/resume 是 bootstrap.md 独有且受权限约束**：写 `{INSTRUCTION_FILE}` §项目状态 是 orchestrator 独占权限，bootstrap.md 已采取**委托**而非内嵌（指向 ORCHESTRATOR-PROTOCOLS §Project Bootstrap）。

## 3. 命名决策（决策记录）

候选与取舍：

| 候选 | 取舍 |
|------|------|
| `framework-bootstrap` | ✗ 与 CLI `cataforge bootstrap` 同名，造成"是 CLI 还是 skill"的歧义 |
| `framework-reconcile` | ✗ 准确描述 upgrade/deploy，但对 init/resume 语义偏弱 |
| `framework-sync` | △ 准确但与 git-sync 概念有潜在歧义 |
| **`framework-update`** | ✓ 落入既有 `framework-*` 家族（review / walkthrough / feedback / issue-resolve）；触发关键词直指"升级/更新"；与 verb 模式 `check` / `apply` / `verify` 读起来自然（沿用 self-update 的 verb，迁移摩擦最小） |

**选定 `framework-update`**。重新评估条件：若 init 路径未来复杂到需独立 skill，则拆分。

## 4. `framework-update` skill 设计

### 4.1 Frontmatter

```yaml
name: framework-update
argument-hint: "[check | apply [--dry-run] [--upgrade-package] | verify]"
suggested-tools: Bash, Read, Edit
depends: []
disable-model-invocation: false
user-invocable: true
```

`user-invocable: true` → 直接 `/framework-update` 即可调用，无需命令包装。

### 4.2 Verb 模式

| 模式 | 来源 | 行为 |
|------|------|------|
| `check` | self-update check | 只读：报 `installed_version` vs `scaffold_version`，以及 `{INSTRUCTION_FILE}` 是否存在（→ 需 init / 已初始化）。不写盘 |
| `apply`（默认） | self-update apply + bootstrap.md | 完整链路，见 4.3 |
| `verify` | self-update verify | 仅 `cataforge doctor`，解读 PASS/SKIP/FAIL |

### 4.3 `apply` 链路（脊柱只描述一次）

```
1. [前置] 包升级（仅当探测到包落后 或 --upgrade-package；--dry-run 跳过）
     探测包管理器（uv → pip 短路）→ uv tool upgrade / pip install -U
     探测失败不 abort：跳过本步，继续刷 scaffold（解耦"升级包"与"刷 scaffold"）
2. [脊柱] cataforge bootstrap --dry-run → 展示 plan → 用户确认 → cataforge bootstrap --yes
     仅 doctor 跑 = "已 current"；fresh install 缺平台时问用户（claude-code 默认）
     upgrade 范围含 CHANGELOG ### BREAKING 时先摘要给用户
3. [后置·簿记] upgrade.state 写入 + {INSTRUCTION_FILE} 框架版本同步 + cataforge claude-md check（hygiene，非阻塞）
4. [后置·分支] 依 {INSTRUCTION_FILE} 是否存在：
     缺  → 委托 ORCHESTRATOR-PROTOCOLS §Project Bootstrap（不内嵌协议）
     在  → cataforge setup --emit-env-block / --apply-permissions → 交接 /start-orchestrator continue
```

字段保留规则（`framework.json` 的 `runtime.platform` / `upgrade.state` 保留、其余覆盖；快照回滚走 `cataforge upgrade rollback`）原样从 self-update 继承。

## 5. 关键约束：权限边界

`apply` 第 4 步 init 分支会写 `{INSTRUCTION_FILE}` §项目状态 —— **orchestrator 独占写权限**。约束：

- `framework-update` 必须由 **orchestrator 主线程内联调用**（用户直接 `/framework-update` 即在主线程运行）；init 分支**不得**派发给子代理执行。
- init 分支只**委托**到 ORCHESTRATOR-PROTOCOLS §Project Bootstrap，skill 本体保持薄壳，不内嵌协议。
- skill 的 Anti-Patterns 显式写明这条边界。

> 实际风险低：init 分支仅在 `{INSTRUCTION_FILE}` 缺失（全新项目）时触发，此时 SDLC 未启动、无子代理运行，主线程即 orchestrator。Anti-Pattern 承担边界声明，无需命令包装来"锚定主上下文"。

## 6. command 移除决策

`/bootstrap` command 是对 skill 的纯重复包装：`framework-update` 既 `user-invocable` 又 model-invocable，`/framework-update` 直接在主上下文运行，权限边界由 §5 的 Anti-Pattern 承担 —— 命令包装不提供任何额外保障。**移除 `.cataforge/commands/bootstrap.md`**（该目录随之清空）。

`/bootstrap` 入口的发现性由两条通道兜底：(1) CLI `cataforge bootstrap` 仍在；(2) skill description 含「bootstrap 或刷新项目脚手架、初始化/恢复项目」触发关键词，自然语言可发现。

## 7. 迁移爆炸半径（已落地）

净 skill 数 1→1（self-update 删、framework-update 增；bootstrap.md 是 command 不计入），故 `check_skill_count.py` 与 README/docs 计数无漂移。

| # | 文件 | 改动 |
|---|------|------|
| 1 | `.cataforge/skills/framework-update/SKILL.md` | 新建（合并 toolkit；无「## Layer 1 检查项」段以免触发 B3-α） |
| 2 | `.cataforge/skills/self-update/` | 删除 |
| 3 | `.cataforge/commands/bootstrap.md` | 删除（目录清空） |
| 4 | `src/.../framework_review/_constants.py` | `ORPHAN_SKILL_WHITELIST`：`self-update` → `framework-update`（B2-α 执行体） |
| 5 | `.cataforge/skills/framework-review/SKILL.md` | B2-α 散文白名单同步（与执行体成对） |
| 6 | `src/.../cli/upgrade_cmd.py` | Tip 文案 `/self-update` → `/framework-update` |
| 7 | `.cataforge/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md` | §Project Bootstrap 引用改指 `framework-update apply` |
| 8 | `.cataforge/scripts/framework/setup.py` | docstring `/bootstrap` 引用改指 `framework-update apply` |
| 9 | `docs/guide/upgrade.md` | `/self-update` / `/bootstrap` → `/framework-update` |
| 10 | `docs/reference/configuration.md` | `self-update` skill → `framework-update` |
| 11 | `docs/reference/agents-and-skills.md` | 4 处 self-update → framework-update（含合并语义） |

不需改动：`check_skill_count.py`（按目录数动态计数，净 0）；deploy 测试（均用自建 fixture，不依赖真实 `bootstrap.md`）。

## 8. 风险与回退

| 风险 | 缓解 |
|------|------|
| init 分支越权写 §项目状态 | §5 约束 + skill Anti-Patterns 显式禁派发 |
| 白名单双轨（散文 vs 执行体）漏改 | §7 步骤 4+5 成对改；framework-review B2-α 复跑自检 |
| 删 `/bootstrap` / `/self-update` 破坏肌肉记忆 | description 触发关键词覆盖；CLI `cataforge bootstrap` 仍在；CHANGELOG 标注入口迁移 |
| 空 `.cataforge/commands/` 目录 | 命令为可选资产，deploy 容忍无命令；目录不被 git 跟踪自然消失 |

回退：元资产层改动，走标准 feature branch + PR；未合入前不影响现有 `/bootstrap` 与 `/self-update`。
