# Phase 0: 目录结构重构 — `.claude/` 解耦

> 前置条件: 无（最先执行）
> 预计工时: 3-5 天
> 动机: `.claude/` 是 Claude Code 的平台约定目录。CataForge 框架核心（agents、skills、rules、scripts、hooks、schemas）属于平台无关逻辑，不应寄生在任何平台的专用目录下。

---

## 问题分析

### 当前状态

`.claude/` 混合了两类不同性质的内容:


| 内容                                                                                                  | 性质                                                         | 文件数 |
| --------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- | --- |
| `settings.json`                                                                                     | **Claude Code 平台专属**（$schema 指向 claude-code-settings.json） | 1   |
| `agents/`, `skills/`, `rules/`, `schemas/`, `scripts/`, `hooks/`, `integrations/`, `framework.json` | **CataForge 框架核心**（平台无关的编排逻辑）                              | 87  |


88 个文件中只有 1 个是真正的平台专属配置，其余 87 个都是框架自身逻辑。

### 影响范围


| 引用来源                                   | `.claude/` 引用行数 | 说明                                                     |
| -------------------------------------- | --------------- | ------------------------------------------------------ |
| 各 AGENT.md / SKILL.md（`.claude/` 内部互引） | ~100+           | `python .claude/scripts/...`、`load .claude/skills/...` |
| CLAUDE.md                              | 6               | 文档导航、框架配置路径                                            |
| tests/snapshots/                       | ~217            | 渲染后的系统提示快照（批量更新）                                       |
| tests/test_*.py                        | ~15             | 框架完整性测试的路径硬编码                                          |
| README.md                              | ~15             | 使用指南                                                   |
| settings.json hooks 命令                 | 8               | `$CLAUDE_PROJECT_DIR/.claude/hooks/*.py`               |
| settings.json permissions              | 3               | `Bash(python .claude/scripts/...)`                     |
| setup.py 完整性检查                         | 9               | 目录/文件存在性校验                                             |


---

## 新目录结构

### 设计原则

1. `**.cataforge/`** = 框架核心（平台无关），是所有内容的 **single source of truth**
2. `**.claude/`** = Claude Code 平台适配层（瘦壳），仅含 `settings.json` + 由同步脚本生成的目录
3. `**.cursor/`、`.codex/`、`.opencode/**` = 其他平台适配层（全部由同步脚本生成）
4. **同步机制**: `platform_sync.py` 负责从 `.cataforge/` 生成各平台目录

### 目标结构

```
.cataforge/                          # CataForge 框架核心（平台无关）
├── framework.json                   # 框架配置（含 runtime.platform）
├── runtime/                         # 跨平台运行时抽象（Phase 1 新建）
│   ├── __init__.py
│   ├── types.py
│   ├── interfaces.py
│   ├── result_parser.py
│   ├── tool_map.yaml
│   ├── hook_bridge.py               # Phase 3
│   └── adapters/                    # Phase 1-2
│       ├── __init__.py
│       ├── _registry.py
│       ├── claude_code.py
│       ├── cursor.py                # Phase 2
│       ├── codex.py                 # Phase 2
│       └── opencode.py              # Phase 2
├── agents/                          # Agent 规范定义
│   ├── orchestrator/
│   │   ├── AGENT.md
│   │   └── ORCHESTRATOR-PROTOCOLS.md
│   ├── architect/AGENT.md
│   ├── implementer/AGENT.md
│   └── ... (13 个 Agent)
├── skills/                          # 22 个 Skill
│   ├── agent-dispatch/
│   │   ├── SKILL.md
│   │   └── templates/dispatch-prompt.md
│   ├── tdd-engine/SKILL.md
│   └── ... (22 个 Skill)
├── rules/                           # 框架规则
│   ├── COMMON-RULES.md
│   └── SUB-AGENT-PROTOCOLS.md
├── schemas/                         # JSON Schema
│   ├── agent-result.schema.json
│   └── event-log.schema.json
├── scripts/                         # 框架脚本
│   ├── framework/
│   │   ├── setup.py
│   │   ├── event_logger.py
│   │   ├── upgrade.py
│   │   ├── phase_reader.py
│   │   ├── platform_sync.py        # 新增: 平台同步脚本
│   │   └── ...
│   └── docs/
│       ├── load_section.py
│       └── build_doc_index.py
├── hooks/                           # Hook 逻辑（跨平台实现）
│   ├── _hook_base.py
│   ├── guard_dangerous.py
│   ├── log_agent_dispatch.py
│   ├── validate_agent_result.py
│   ├── lint_format.py
│   ├── detect_correction.py
│   ├── notify_done.py
│   ├── notify_permission.py
│   ├── notify_util.py
│   └── session_context.py
└── integrations/
    └── penpot/setup_penpot.py

.claude/                             # Claude Code 平台适配层（瘦壳）
├── settings.json                    # 唯一手动维护文件
├── agents/                          # ← platform_sync 从 .cataforge/agents/ 生成
│   └── (junction/symlink/copy)
└── rules/                           # ← platform_sync 从 .cataforge/rules/ 生成
    └── (junction/symlink/copy)

.cursor/                             # Cursor 适配（Phase 2 由 platform_sync 生成）
├── hooks.json
├── rules/                           # MDC 格式（从 .cataforge/rules/ 转换）
└── agents/                          # 可选（Cursor 已扫描 .claude/agents/）

.codex/                              # Codex 适配（Phase 2 由 platform_sync 生成）
├── agents/                          # TOML 格式（从 .cataforge/agents/ 转换）
└── hooks.json

CLAUDE.md                            # 项目指令（引用 .cataforge/ 路径）
```

### 关键设计决策

#### 为什么 `.claude/agents/` 和 `.claude/rules/` 仍然存在？

Claude Code 平台有两个硬约束:

- `subagent_type` 参数从 `.claude/agents/{name}/AGENT.md` 加载 Agent 定义
- `.claude/rules/` 下的文件自动注入 LLM 上下文

这些行为不可配置，因此 `.claude/agents/` 和 `.claude/rules/` 必须存在。但它们**不是源文件**，而是由 `platform_sync.py` 从 `.cataforge/` 生成的。

#### 同步机制: junction vs symlink vs copy


| 方式                                   | Windows   | macOS/Linux | 优点     | 缺点         |
| ------------------------------------ | --------- | ----------- | ------ | ---------- |
| **Directory Junction** (`mklink /J`) | 无需管理员权限 ✓ | N/A         | 透明、零开销 | 仅 Windows  |
| **Symlink** (`ln -s`)                | 需管理员权限 ✗  | 原生支持 ✓      | 透明、零开销 | Windows 受限 |
| **复制**                               | 通用 ✓      | 通用 ✓        | 无权限问题  | 需手动同步      |


**策略**: `platform_sync.py` 自动检测操作系统:

- macOS/Linux → symlink
- Windows → 优先尝试 junction，失败则回退到复制

#### `.claude/settings.json` 路径更新

settings.json 中的 hook 命令路径更新为指向 `.cataforge/hooks/`:

```json
"command": "python \"$CLAUDE_PROJECT_DIR/.cataforge/hooks/guard_dangerous.py\""
```

permissions 中的脚本路径同理:

```json
"Bash(python .cataforge/scripts/framework/*.py*)",
"Bash(python .cataforge/scripts/docs/*.py*)",
"Bash(python .cataforge/skills/*/scripts/*.py*)"
```

---

## 执行步骤

### Step 0.1: 创建 `.cataforge/` 目录并移动文件

```bash
# 创建目标目录
mkdir -p .cataforge

# 移动框架核心文件（保留 git 历史）
git mv .claude/framework.json .cataforge/
git mv .claude/agents .cataforge/
git mv .claude/skills .cataforge/
git mv .claude/rules .cataforge/
git mv .claude/schemas .cataforge/
git mv .claude/scripts .cataforge/
git mv .claude/hooks .cataforge/
git mv .claude/integrations .cataforge/

# .claude/ 仅保留 settings.json
# settings.json 留在 .claude/（Claude Code 专属配置）
```

### Step 0.2: 创建 platform_sync.py

新增: `.cataforge/scripts/framework/platform_sync.py`

```python
"""CataForge 平台同步脚本。

从 .cataforge/（canonical source）生成各平台所需的目录结构。

用法:
  python .cataforge/scripts/framework/platform_sync.py [--platform claude-code|cursor|codex|opencode|all]
  python .cataforge/scripts/framework/platform_sync.py --check  # 检查同步状态
"""
import argparse
import json
import os
import platform
import shutil
import sys
from pathlib import Path


def get_project_root() -> Path:
    """获取项目根目录（.cataforge/ 的父目录）。"""
    return Path(__file__).resolve().parents[3]


def create_link(source: Path, target: Path) -> str:
    """创建目录链接。返回使用的方式。"""
    if target.exists() or target.is_symlink():
        if target.is_symlink() or _is_junction(target):
            target.unlink() if target.is_symlink() else _remove_junction(target)
        elif target.is_dir():
            shutil.rmtree(target)

    target.parent.mkdir(parents=True, exist_ok=True)

    if platform.system() != "Windows":
        rel = os.path.relpath(source, target.parent)
        target.symlink_to(rel)
        return "symlink"

    # Windows: 优先 junction
    try:
        import subprocess
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target), str(source)],
            check=True, capture_output=True,
        )
        return "junction"
    except (subprocess.CalledProcessError, FileNotFoundError):
        shutil.copytree(source, target)
        return "copy"


def sync_claude_code(root: Path) -> list[str]:
    """生成 .claude/ 目录结构。"""
    cataforge = root / ".cataforge"
    claude = root / ".claude"
    claude.mkdir(exist_ok=True)
    actions = []

    for dirname in ("agents", "rules"):
        src = cataforge / dirname
        dst = claude / dirname
        if src.is_dir():
            method = create_link(src, dst)
            actions.append(f".claude/{dirname}/ ← .cataforge/{dirname}/ ({method})")

    return actions


def sync_cursor(root: Path) -> list[str]:
    """生成 .cursor/ 目录结构。"""
    # Cursor 已原生扫描 .claude/agents/，无需额外操作
    # hooks.json 和 rules/ 由 Phase 2 cursor_hooks.py / cursor_rules_gen.py 生成
    return ["cursor: 依赖 .claude/agents/ 扫描（由 sync_claude_code 保证）"]


def sync_codex(root: Path) -> list[str]:
    """生成 .codex/ 目录结构。"""
    # TOML 转换由 Phase 2 codex_definition.py 处理
    return ["codex: agents TOML 由 codex_definition.sync_agents_to_codex() 生成"]


def check_sync(root: Path) -> list[str]:
    """检查同步状态，返回问题列表。"""
    issues = []
    cataforge = root / ".cataforge"
    claude = root / ".claude"

    if not cataforge.is_dir():
        issues.append("ERROR: .cataforge/ 目录不存在")
        return issues

    for dirname in ("agents", "rules"):
        src = cataforge / dirname
        dst = claude / dirname
        if not src.is_dir():
            issues.append(f"ERROR: .cataforge/{dirname}/ 不存在")
        elif not dst.exists():
            issues.append(f"WARN: .claude/{dirname}/ 不存在（需运行 sync）")
        elif dst.is_symlink() or _is_junction(dst):
            pass  # OK - linked
        elif dst.is_dir():
            issues.append(f"INFO: .claude/{dirname}/ 是独立副本（非链接）")

    return issues


def _is_junction(path: Path) -> bool:
    """检查是否为 Windows directory junction。"""
    if platform.system() != "Windows":
        return False
    try:
        import ctypes
        attr = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        return bool(attr & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except Exception:
        return False


def _remove_junction(path: Path):
    """移除 Windows directory junction。"""
    try:
        os.rmdir(str(path))
    except OSError:
        shutil.rmtree(str(path))


def main():
    parser = argparse.ArgumentParser(description="CataForge 平台同步")
    parser.add_argument(
        "--platform",
        choices=["claude-code", "cursor", "codex", "opencode", "all"],
        default="all",
    )
    parser.add_argument("--check", action="store_true", help="仅检查同步状态")
    args = parser.parse_args()

    root = get_project_root()

    if args.check:
        issues = check_sync(root)
        if issues:
            for issue in issues:
                print(issue)
            sys.exit(1)
        else:
            print("✓ 平台同步状态正常")
            sys.exit(0)

    targets = (
        ["claude-code", "cursor", "codex", "opencode"]
        if args.platform == "all"
        else [args.platform]
    )

    for target in targets:
        if target == "claude-code":
            actions = sync_claude_code(root)
        elif target == "cursor":
            actions = sync_cursor(root)
        elif target == "codex":
            actions = sync_codex(root)
        else:
            actions = [f"{target}: 同步逻辑待实现"]

        for action in actions:
            print(f"  [{target}] {action}")


if __name__ == "__main__":
    main()
```

### Step 0.3: 更新 `.claude/settings.json` 路径

所有 hook 命令路径从 `.claude/hooks/` 改为 `.cataforge/hooks/`:


| 行号   | 旧路径                                      | 新路径                                         |
| ---- | ---------------------------------------- | ------------------------------------------- |
| L63  | `.claude/hooks/guard_dangerous.py`       | `.cataforge/hooks/guard_dangerous.py`       |
| L72  | `.claude/hooks/log_agent_dispatch.py`    | `.cataforge/hooks/log_agent_dispatch.py`    |
| L83  | `.claude/hooks/lint_format.py`           | `.cataforge/hooks/lint_format.py`           |
| L92  | `.claude/hooks/validate_agent_result.py` | `.cataforge/hooks/validate_agent_result.py` |
| L101 | `.claude/hooks/detect_correction.py`     | `.cataforge/hooks/detect_correction.py`     |
| L112 | `.claude/hooks/notify_done.py`           | `.cataforge/hooks/notify_done.py`           |
| L123 | `.claude/hooks/notify_permission.py`     | `.cataforge/hooks/notify_permission.py`     |
| L134 | `.claude/hooks/session_context.py`       | `.cataforge/hooks/session_context.py`       |


permissions 路径:


| 行号  | 旧路径                                            | 新路径                                               |
| --- | ---------------------------------------------- | ------------------------------------------------- |
| L24 | `Bash(python .claude/skills/*/scripts/*.py*)`  | `Bash(python .cataforge/skills/*/scripts/*.py*)`  |
| L25 | `Bash(python .claude/scripts/framework/*.py*)` | `Bash(python .cataforge/scripts/framework/*.py*)` |
| L26 | `Bash(python .claude/scripts/docs/*.py*)`      | `Bash(python .cataforge/scripts/docs/*.py*)`      |
| L27 | `Bash(python .claude/integrations/penpot/...)` | `Bash(python .cataforge/integrations/penpot/...)` |


### Step 0.4: 更新框架内部路径引用

#### CLAUDE.md (6 处)


| 行   | 旧                                                       | 新                                                          |
| --- | ------------------------------------------------------- | ---------------------------------------------------------- |
| L23 | `python .claude/scripts/framework/setup.py`             | `python .cataforge/scripts/framework/setup.py`             |
| L45 | `.claude/rules/COMMON-RULES.md`                         | `.cataforge/rules/COMMON-RULES.md`                         |
| L46 | `.claude/rules/SUB-AGENT-PROTOCOLS.md`                  | `.cataforge/rules/SUB-AGENT-PROTOCOLS.md`                  |
| L47 | `.claude/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md` | `.cataforge/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md` |
| L48 | `.claude/schemas/agent-result.schema.json`              | `.cataforge/schemas/agent-result.schema.json`              |
| L76 | `.claude/framework.json`                                | `.cataforge/framework.json`                                |


#### Hook 脚本内部的相对路径

所有 hook 脚本中 `os.path.join(os.path.dirname(__file__), "..", "scripts")` 模式不变（因为移动后 `.cataforge/hooks/` 和 `.cataforge/scripts/` 的相对位置与 `.claude/hooks/` 和 `.claude/scripts/` 完全一致）。

#### setup.py 完整性检查（L481-499）

```python
# 旧
".claude/agents",
".claude/skills",
".claude/rules",
".claude/hooks",
".claude/scripts",
# ...
".claude/rules/COMMON-RULES.md",

# 新
".cataforge/agents",
".cataforge/skills",
".cataforge/rules",
".cataforge/hooks",
".cataforge/scripts",
# ...
".cataforge/rules/COMMON-RULES.md",
```

#### AGENT.md 内部引用（分批处理）

含 `.claude/` 引用的 8 个 AGENT.md:


| Agent        | 引用内容                                                  | 变更                                                 |
| ------------ | ----------------------------------------------------- | -------------------------------------------------- |
| orchestrator | `ORCHESTRATOR-PROTOCOLS.md` 引用、`schemas/`             | 路径前缀 `.claude/` → `.cataforge/`                    |
| architect    | `python .claude/scripts/docs/load_section.py`         | → `python .cataforge/scripts/docs/load_section.py` |
| ui-designer  | 同上                                                    | 同上                                                 |
| qa-engineer  | 同上                                                    | 同上                                                 |
| devops       | 同上                                                    | 同上                                                 |
| tech-lead    | `load_section.py` + `dep_analysis.py`                 | 同上                                                 |
| debugger     | `.claude/scripts/`、`.claude/hooks/`、`.claude/skills/` | → `.cataforge/...`                                 |
| reflector    | `.claude/learnings/`                                  | → `.cataforge/learnings/`                          |


不含引用的 5 个（无需修改）: `product-manager`, `implementer`, `reviewer`, `refactorer`, `test-writer`

#### SKILL.md 内部引用（12 个含引用）

所有 12 个含 `.claude/` 的 SKILL.md 中的路径前缀统一替换:

```
.claude/scripts/framework/  → .cataforge/scripts/framework/
.claude/scripts/docs/        → .cataforge/scripts/docs/
.claude/skills/              → .cataforge/skills/
.claude/agents/              → .cataforge/agents/
.claude/schemas/             → .cataforge/schemas/
.claude/hooks/               → .cataforge/hooks/
.claude/integrations/        → .cataforge/integrations/
.claude/settings.json        → .claude/settings.json (保留!)
.claude/framework.json       → .cataforge/framework.json
.claude/learnings/           → .cataforge/learnings/
```

注意: `.claude/settings.json` 引用**保持不变**（它确实是 Claude Code 平台专属文件）。

#### ORCHESTRATOR-PROTOCOLS.md

该文件内含大量 `python .claude/scripts/framework/event_logger.py` 调用，全部替换为 `python .cataforge/scripts/framework/event_logger.py`。
`--apply-permissions` 中提到的 `.claude/settings.json` 保持不变。

### Step 0.5: 运行 platform_sync 建立 `.claude/` 链接

```bash
python .cataforge/scripts/framework/platform_sync.py --platform claude-code
```

验证:

```bash
python .cataforge/scripts/framework/platform_sync.py --check
```

### Step 0.6: 更新测试快照

```bash
# 重新生成所有快照（路径变更会导致快照不匹配）
python -m pytest tests/ --snapshot-update
```

同时更新 `test_framework_integrity.py` 和 `test_upgrade_merge.py` 中的硬编码路径。

### Step 0.7: 更新 README.md

将所有安装/使用指南中的 `.claude/` 路径更新为 `.cataforge/`。

### Step 0.8: 更新 .gitignore

```gitignore
# Platform-generated directories (由 platform_sync 生成)
.claude/agents/
.claude/rules/

# Keep only settings.json in .claude/
!.claude/settings.json
```

---

## 文件变更统计


| 操作              | 数量  | 说明                                                                                                                     |
| --------------- | --- | ---------------------------------------------------------------------------------------------------------------------- |
| **移动** (git mv) | 87  | `.claude/` → `.cataforge/`（除 `settings.json` 外全部）                                                                      |
| **新增**          | 1   | `platform_sync.py`                                                                                                     |
| **修改**          | ~40 | settings.json + CLAUDE.md + 8 AGENT.md + 12 SKILL.md + ORCHESTRATOR-PROTOCOLS.md + setup.py + README.md + 2 test files |
| **快照更新**        | ~19 | tests/snapshots/ 批量更新                                                                                                  |


---

## 验收标准


| #      | 标准                                                                                                         | 验证方式                |
| ------ | ---------------------------------------------------------------------------------------------------------- | ------------------- |
| AC-0.1 | `.cataforge/` 包含所有框架核心文件（agents/skills/rules/schemas/scripts/hooks/integrations/framework.json）            | `ls .cataforge/`    |
| AC-0.2 | `.claude/` 仅含 `settings.json` + 链接目录（agents/, rules/）                                                      | `ls .claude/` 仅 3 项 |
| AC-0.3 | `platform_sync.py --check` 通过                                                                              | 返回 exit code 0      |
| AC-0.4 | `settings.json` 所有 hook 命令指向 `.cataforge/hooks/`                                                           | grep 验证             |
| AC-0.5 | 全部 SKILL.md/AGENT.md 中无 `.claude/skills/`、`.claude/agents/`、`.claude/scripts/`（`.claude/settings.json` 例外） | grep 验证             |
| AC-0.6 | `pytest tests/` 全部通过（快照更新后）                                                                                | CI 运行               |
| AC-0.7 | Claude Code 的 `Agent(subagent_type="architect")` 仍能正确加载 AGENT.md                                           | 手动验证                |


---

## 风险项


| 风险                            | 影响                                            | 缓解方案                                             |
| ----------------------------- | --------------------------------------------- | ------------------------------------------------ |
| Windows directory junction 失败 | `.claude/agents/` 不存在 → Claude Code 找不到 Agent | 自动回退到复制模式；setup.py 中添加同步检查                       |
| Git 不跟踪 symlink 目标内容          | 其他开发者 clone 后 `.claude/agents/` 为空            | 在 setup.py 初始化流程中自动运行 `platform_sync.py`         |
| 升级脚本 (upgrade.py) 路径假设        | 升级脚本可能仍假设文件在 `.claude/`                       | 升级脚本同步更新路径映射                                     |
| CI/CD 环境中 symlink 行为差异        | CI 容器中可能不支持                                   | platform_sync 默认 copy 模式 + `--link-mode copy` 参数 |


---

## 与后续 Phase 的关系

Phase 0 完成后:

- **Phase 1** 的 runtime 包直接创建在 `.cataforge/runtime/`（而非 `.claude/runtime/`）
- **Phase 2** 的适配器在 `.cataforge/runtime/adapters/`
- **Phase 3** 的 hook 改造在 `.cataforge/hooks/`
- **Phase 4** 的测试路径全部基于 `.cataforge/`

所有后续 Phase 的路径引用以 `.cataforge/` 为准。