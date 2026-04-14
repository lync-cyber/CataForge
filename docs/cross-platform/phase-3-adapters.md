# Phase 3: 平台适配器

> 前置条件：Phase 2 完成（`.cataforge/` 目录、deploy 基础可运行）
> 预计工时：2-3 周
> 优先级：P0 Claude Code（身份适配） → P1 Cursor（Phase 0 已验证） → P2 OpenCode → P3 Codex

---

## 架构说明

v2 方案中**没有 Dispatcher 抽象接口**（D-7）。每个平台适配器是一个 `deploy_*.py` 模块，负责：

1. 读取 `profile.yaml` 中的平台声明
2. 调用 runtime 工具层（frontmatter_translator、template_renderer、hook_bridge）
3. 生成平台专属的部署产物

适配器不负责运行时调度（调度由 LLM 通过 override 后的 prompt 模板驱动），只负责 deploy 时的格式转换。

---

## Step 3.1: Claude Code 适配（P0 — 身份适配）

Claude Code 是基础模板的默认目标，适配工作最少。

### deploy 行为


| 步骤        | 输入                                    | 输出                                  |
| --------- | ------------------------------------- | ----------------------------------- |
| Agent 翻译  | `.cataforge/agents/*/AGENT.md` (能力ID) | `.claude/agents/*/AGENT.md` (原生名)   |
| 指令生成      | `.cataforge/PROJECT-STATE.md`         | `CLAUDE.md`                         |
| Rules 链接  | `.cataforge/rules/`                   | `.claude/rules/` (symlink/junction) |
| Prompt 渲染 | dispatch-prompt.md (无 override)       | 直接使用基础模板                            |
| Hook 配置   | 不修改 `.claude/settings.json`           | 仅验证路径指向 `.cataforge/hooks/`         |


### 新增：`.cataforge/platforms/claude-code/overrides/`

Claude Code 作为基础模板默认目标，overrides 目录为空（或不存在）。基础模板中 `<!-- OVERRIDE:xxx -->` 标记的默认内容即为 Claude Code 的行为。

### 验收标准


| #        | 标准                                                                     |
| -------- | ---------------------------------------------------------------------- |
| AC-3.1.1 | `deploy --platform claude-code` 后 `.claude/agents/` 中 AGENT.md 使用原生工具名 |
| AC-3.1.2 | `CLAUDE.md` 中 `运行时: claude-code`                                       |
| AC-3.1.3 | `Agent(subagent_type="architect")` 正常加载                                |


---

## Step 3.2: Cursor 适配（P1 — Phase 0 已验证）

### 前置：Phase 0 验证结论

本步骤的具体实现取决于 Phase 0 验证结果。以下基于假设全部 PASS 的设计。

### deploy 行为


| 步骤        | 输入                                      | 输出                                         |
| --------- | --------------------------------------- | ------------------------------------------ |
| Agent 翻译  | `.cataforge/agents/*/AGENT.md`          | `.claude/agents/*/AGENT.md` (Cursor 扫描此目录) |
| 指令生成      | `.cataforge/PROJECT-STATE.md`           | `CLAUDE.md` + `.cursor/rules/*.mdc`        |
| Hook 配置   | `.cataforge/hooks/hooks.yaml` + profile | `.cursor/hooks.json`                       |
| Prompt 渲染 | dispatch-prompt.md + cursor override    | 合并后模板（运行时使用）                               |


### Cursor 特殊处理

#### Agent 定义

Cursor 原生扫描 `.claude/agents/`（Phase 0 H-1 验证）。deploy 将翻译后的 AGENT.md 写入 `.claude/agents/`（与 Claude Code 共用目标目录，但 tool_map 不同）。

**多平台冲突问题**：如果同一项目同时在 Claude Code 和 Cursor 中使用，`.claude/agents/` 中的 AGENT.md 翻译结果会不同。

**解决方案**：deploy 接受 `--platform` 参数，每次 deploy 生成指定平台的产物。切换平台时重新 deploy。SessionStart hook 自动检测当前平台并 deploy。

#### MDC Rules 生成

`.cursor/rules/` 使用 MDC 格式（YAML frontmatter + Markdown）。

### 新增：Cursor rules 生成模块

```python
# .cataforge/platforms/cursor/deploy_rules.py
"""从 .cataforge/rules/ + overrides 生成 .cursor/rules/ MDC 文件。"""
from __future__ import annotations
import os
import re
from pathlib import Path


def generate_cursor_rules(
    cataforge_rules_dir: Path,
    overrides_rules_dir: Path | None,
    output_dir: Path,
) -> list[str]:
    """生成 .cursor/rules/ 目录。

    策略:
    1. .cataforge/rules/*.md → .cursor/rules/*.mdc (添加 MDC frontmatter)
    2. overrides/rules/*.md → .cursor/rules/*.mdc (平台专属规则)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = []

    # 转换通用规则
    for md_file in sorted(cataforge_rules_dir.glob("*.md")):
        mdc_name = md_file.stem.lower() + ".mdc"
        mdc_path = output_dir / mdc_name
        _convert_to_mdc(md_file, mdc_path, always_apply=True)
        generated.append(str(mdc_path))

    # 添加平台专属规则
    if overrides_rules_dir and overrides_rules_dir.is_dir():
        for md_file in sorted(overrides_rules_dir.glob("*.md")):
            mdc_name = md_file.stem.lower() + ".mdc"
            mdc_path = output_dir / mdc_name
            _convert_to_mdc(md_file, mdc_path, always_apply=True)
            generated.append(str(mdc_path))

    return generated


def _convert_to_mdc(source: Path, target: Path, always_apply: bool = False):
    """Markdown → MDC 格式转换。"""
    content = source.read_text(encoding="utf-8")
    title = _extract_title(content)
    frontmatter = (
        f'---\ndescription: "{title}"\n'
        f'alwaysApply: {str(always_apply).lower()}\n---\n\n'
    )
    target.write_text(frontmatter + content, encoding="utf-8")


def _extract_title(content: str) -> str:
    m = re.match(r"^#\s+(.+)", content)
    return m.group(1).strip() if m else "CataForge Rule"
```

### Cursor Hook 配置生成

由 Phase 4 的 `hook_bridge.py` 实现（从 `hooks.yaml` + cursor profile 的 `event_map`/`matcher_map` 生成 `.cursor/hooks.json`）。

### 验收标准


| #        | 标准                                                                          |
| -------- | --------------------------------------------------------------------------- |
| AC-3.2.1 | `deploy --platform cursor` 生成 `.cursor/rules/*.mdc`                         |
| AC-3.2.2 | MDC 文件含 `alwaysApply: true` 和合法 YAML frontmatter                            |
| AC-3.2.3 | `.claude/agents/` 中 AGENT.md 使用 Cursor 原生工具名（`StrReplace`, `Shell`, `Task`） |
| AC-3.2.4 | Cursor 中 `Task(subagent_type="architect")` 正常加载                             |


---

## Step 3.3: OpenCode 适配（P2）

### deploy 行为

OpenCode 与 Claude Code 最兼容：

- Agent 定义：原生扫描 `.claude/agents/`，格式兼容 → profile 中 `needs_deploy: false`
- 指令文件：原生读取 `CLAUDE.md` → 无额外产出
- Hooks：无原生 Hook 系统 → 全部降级

**注意**：profile.yaml 中 `needs_deploy: false` 意味着 OpenCode 直接读取 Claude Code deploy 后的 `.claude/agents/`。如果用户从 Cursor 切换到 OpenCode，需要先 `deploy --platform opencode`（实际上是 `deploy --platform claude-code` 因为产物相同）。

### 验收标准


| #        | 标准                                                      |
| -------- | ------------------------------------------------------- |
| AC-3.3.1 | `deploy --platform opencode` 不生成额外文件（依赖 claude-code 产物） |
| AC-3.3.2 | profile.yaml opencode 段正确声明 `needs_deploy: false`       |


---

## Step 3.4: Codex CLI 适配（P3）

### deploy 行为

Codex 差异最大，需要格式转换：


| 步骤       | 输入                                                       | 输出                            |
| -------- | -------------------------------------------------------- | ----------------------------- |
| Agent 转换 | `.cataforge/agents/*/AGENT.md` (YAML FM)                 | `.codex/agents/*.toml` (TOML) |
| 指令文件     | Codex 配置 `project_doc_fallback_filenames: ["CLAUDE.md"]` | 无额外文件                         |
| Hook 配置  | `.cataforge/hooks/hooks.yaml` + profile                  | `.codex/hooks.json`（仅 3 个可映射） |


### 新增：Codex Agent TOML 转换

```python
# .cataforge/platforms/codex/deploy_agents.py
"""AGENT.md YAML frontmatter → Codex TOML 转换。"""
from __future__ import annotations
import os
import re
from pathlib import Path

try:
    import tomli_w
except ImportError:
    tomli_w = None


def convert_agent_to_toml(agent_md_path: Path, platform_id: str = "codex") -> str:
    """将 AGENT.md 转换为 Codex TOML 格式。"""
    content = agent_md_path.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(content)

    if not fm:
        raise ValueError(f"No YAML frontmatter in {agent_md_path}")

    toml_data = {
        "name": fm.get("name", ""),
        "description": fm.get("description", ""),
        "developer_instructions": body.strip(),
    }

    if fm.get("model") and fm["model"] != "inherit":
        toml_data["model"] = fm["model"]

    if tomli_w:
        return tomli_w.dumps(toml_data)
    return _manual_toml(toml_data)


def sync_agents_to_codex(source_dir: Path, codex_dir: Path) -> list[str]:
    """批量转换 .cataforge/agents/ → .codex/agents/。"""
    codex_dir.mkdir(parents=True, exist_ok=True)
    generated = []

    for agent_name in sorted(os.listdir(source_dir)):
        agent_md = source_dir / agent_name / "AGENT.md"
        if not agent_md.is_file():
            continue

        toml_content = convert_agent_to_toml(agent_md)
        toml_path = codex_dir / f"{agent_name}.toml"
        toml_path.write_text(toml_content, encoding="utf-8")
        generated.append(str(toml_path))

    return generated


def _split_frontmatter(content: str):
    import yaml
    m = re.match(r"^---\n(.*?)\n---\n?(.*)", content, re.DOTALL)
    if not m:
        return None, content
    try:
        fm = yaml.safe_load(m.group(1))
    except Exception:
        fm = None
    return fm, m.group(2)


def _manual_toml(data: dict) -> str:
    lines = []
    for key, value in data.items():
        if isinstance(value, str):
            if "\n" in value:
                lines.append(f'{key} = """\n{value}\n"""')
            else:
                lines.append(f'{key} = "{value}"')
    return "\n".join(lines) + "\n"
```

### 验收标准


| #        | 标准                                                          |
| -------- | ----------------------------------------------------------- |
| AC-3.4.1 | `deploy --platform codex` 生成 `.codex/agents/*.toml`         |
| AC-3.4.2 | 生成的 TOML 包含 `name`, `description`, `developer_instructions` |
| AC-3.4.3 | 13 个 AGENT.md 全部转换成功                                        |


---

## deploy 主流程集成

Phase 3 完成后，`runtime/deploy.py` 的 `deploy()` 函数需集成各平台的特殊处理：

```python
def deploy(platform_id: str) -> list[str]:
    profile = load_profile(platform_id)
    actions = []

    # 通用步骤
    actions.extend(_deploy_agents(root, platform_id, profile))
    actions.extend(_deploy_claude_md(root, platform_id, profile))
    actions.extend(_deploy_rules_link(root, platform_id, profile))

    # 平台特殊步骤
    if platform_id == "cursor":
        from platforms.cursor.deploy_rules import generate_cursor_rules
        actions.extend(generate_cursor_rules(...))

    elif platform_id == "codex":
        from platforms.codex.deploy_agents import sync_agents_to_codex
        actions.extend(sync_agents_to_codex(...))

    # Hook 配置（Phase 4 实现）
    actions.extend(_deploy_hooks(root, platform_id, profile))

    return actions
```

---

## 风险项


| 风险                  | 影响                                   | 缓解                                              |
| ------------------- | ------------------------------------ | ----------------------------------------------- |
| 多平台产物冲突             | 同一 `.claude/agents/` 被不同平台 deploy 覆盖 | deploy 记录当前平台到 `.cataforge/.deploy-state`，切换时警告 |
| Codex TOML 必填字段未知   | 生成的 TOML 被拒绝                         | Phase 0 后补充 Codex 验证（或 Phase 3 执行时现场验证）         |
| OpenCode 工具名推测性     | tool_map 映射错误                        | 标记为 `version_tested: "unverified"`，Phase 5 验证   |
| tomli_w / PyYAML 缺失 | TOML 生成失败                            | 提供 manual fallback 格式化                          |


