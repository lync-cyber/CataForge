# Phase 5: 端到端验证与 API 稳定化

> 前置条件：Phase 1-4 全部完成
> 预计工时：1 周
> 目标：完整测试套件、Bootstrap 平台选择、API 版本锁定

---

## Step 5.1: 测试套件

### 测试文件清单

所有测试路径基于 `.cataforge/`（非 `.claude/`）。


| 测试文件                                                | 覆盖范围                                      |
| --------------------------------------------------- | ----------------------------------------- |
| `tests/test_runtime/test_types.py`                  | AgentStatus, DispatchRequest, AgentResult |
| `tests/test_runtime/test_profile_loader.py`         | profile.yaml 加载、tool_map 解析、平台检测          |
| `tests/test_runtime/test_template_renderer.py`      | Override 标记解析、合并逻辑、标记点列举                  |
| `tests/test_runtime/test_frontmatter_translator.py` | 能力标识符翻译、null 能力跳过                         |
| `tests/test_runtime/test_result_parser.py`          | 4 级容错解析                                   |
| `tests/test_runtime/test_hook_bridge.py`            | Hook 配置生成、退化计算                            |
| `tests/test_runtime/test_deploy.py`                 | deploy 端到端（mock 文件系统）                     |


### 关键测试用例

#### test_profile_loader.py

```python
"""测试 profile 加载和工具名解析。"""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".cataforge"))

from runtime.profile_loader import (
    load_profile, get_tool_map, resolve_tool_name, resolve_tools_list,
)


class TestLoadProfile:
    def test_claude_code_profile(self):
        profile = load_profile("claude-code")
        assert profile["platform_id"] == "claude-code"
        assert profile["tool_map"]["shell_exec"] == "Bash"

    def test_cursor_profile(self):
        profile = load_profile("cursor")
        assert profile["tool_map"]["file_edit"] == "StrReplace"
        assert profile["tool_map"]["shell_exec"] == "Shell"
        assert profile["tool_map"]["agent_dispatch"] == "Task"

    def test_all_profiles_have_required_fields(self):
        for pid in ["claude-code", "cursor", "codex", "opencode"]:
            profile = load_profile(pid)
            assert "platform_id" in profile
            assert "tool_map" in profile
            assert "dispatch" in profile
            assert "hooks" in profile


class TestResolveToolName:
    def test_claude_code_dispatch(self):
        assert resolve_tool_name("agent_dispatch", "claude-code") == "Agent"

    def test_cursor_dispatch(self):
        assert resolve_tool_name("agent_dispatch", "cursor") == "Task"

    def test_unsupported_capability_returns_none(self):
        assert resolve_tool_name("user_question", "cursor") is None

    def test_resolve_tools_list_skips_unsupported(self):
        caps = ["file_read", "user_question", "agent_dispatch"]
        result = resolve_tools_list(caps, "cursor")
        assert "Read" in result
        assert "Task" in result
        assert len(result) == 2  # user_question 被跳过
```

#### test_template_renderer.py

```python
"""测试模板 Override 渲染。"""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".cataforge"))

from runtime.template_renderer import render_template, list_override_points


class TestOverridePoints:
    def test_dispatch_prompt_has_expected_points(self):
        points = list_override_points(
            "skills/agent-dispatch/templates/dispatch-prompt.md"
        )
        expected = {"dispatch_syntax", "startup_notes", "return_format",
                    "tool_usage", "context_limits"}
        assert expected == set(points)


class TestRenderTemplate:
    def test_claude_code_uses_defaults(self):
        result = render_template(
            "skills/agent-dispatch/templates/dispatch-prompt.md",
            "claude-code",
        )
        assert "Agent tool:" in result or "subagent_type" in result
        assert "<!-- OVERRIDE:" not in result  # 标记已移除

    def test_cursor_override_applied(self):
        result = render_template(
            "skills/agent-dispatch/templates/dispatch-prompt.md",
            "cursor",
        )
        assert "Task:" in result or "StrReplace" in result
        assert "<!-- OVERRIDE:" not in result
```

#### test_frontmatter_translator.py

```python
"""测试 AGENT.md frontmatter 翻译。"""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".cataforge"))

from runtime.frontmatter_translator import translate_agent_md


class TestTranslateAgentMd:
    SAMPLE_MD = """---
name: orchestrator
tools: file_read, file_write, file_edit, file_glob, file_grep, shell_exec, agent_dispatch, user_question
disallowedTools: []
---
# Role: orchestrator
"""

    def test_claude_code_translation(self):
        result = translate_agent_md(self.SAMPLE_MD, "claude-code")
        assert "tools: Read, Write, Edit, Glob, Grep, Bash, Agent, AskUserQuestion" in result

    def test_cursor_translation(self):
        result = translate_agent_md(self.SAMPLE_MD, "cursor")
        assert "StrReplace" in result
        assert "Shell" in result
        assert "Task" in result
        # user_question is null for Cursor → removed from list
        assert "AskUserQuestion" not in result

    def test_body_unchanged(self):
        result = translate_agent_md(self.SAMPLE_MD, "cursor")
        assert "# Role: orchestrator" in result
```

#### test_hook_bridge.py

```python
"""测试 Hook 桥接层。"""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".cataforge"))

from runtime.hook_bridge import (
    generate_platform_hooks, get_degraded_hooks,
)


class TestGeneratePlatformHooks:
    def test_claude_code_all_native(self):
        hooks = generate_platform_hooks("claude-code")
        assert "PreToolUse" in hooks
        assert "PostToolUse" in hooks
        assert "Stop" in hooks

    def test_cursor_translates_event_names(self):
        hooks = generate_platform_hooks("cursor")
        assert "preToolUse" in hooks
        assert "PreToolUse" not in hooks

    def test_opencode_empty(self):
        hooks = generate_platform_hooks("opencode")
        assert hooks == {}


class TestDegradedHooks:
    def test_claude_code_no_degradation(self):
        degraded = get_degraded_hooks("claude-code")
        assert len(degraded) == 0

    def test_opencode_all_degraded(self):
        degraded = get_degraded_hooks("opencode")
        assert len(degraded) >= 6  # 至少 6 个有退化模板

    def test_codex_partial_degradation(self):
        degraded = get_degraded_hooks("codex")
        names = [d["name"] for d in degraded]
        assert "log_agent_dispatch" in names
        assert "guard_dangerous" not in names  # native
```

---

## Step 5.2: Bootstrap 平台选择

### 修改：`.cataforge/scripts/framework/setup.py`

添加 `--platform` 参数：

```python
parser.add_argument(
    "--platform",
    choices=["claude-code", "cursor", "codex", "opencode"],
    default=None,
    help="设置运行时平台（写入 framework.json runtime.platform）",
)
```

当 `--platform` 提供时：

1. 读取 `framework.json`
2. 设置/更新 `runtime.platform` 字段
3. 运行 `deploy.py --platform {选择}`

### 修改：ORCHESTRATOR-PROTOCOLS.md

在 Bootstrap Step 1 之后插入平台确认步骤：

```markdown
1.5. **确认运行时平台** — 自动检测当前环境，通过 AskUserQuestion 确认:
     - 选项: claude-code（默认）| cursor | codex | opencode
     - 结果写入 framework.json 的 runtime.platform
     - 自动运行 deploy
```

---

## Step 5.3: API 版本锁定

### framework.json 新增字段

```json
{
  "version": "0.3.0",
  "runtime_api_version": "1.0",
  "runtime": {
    "platform": "claude-code"
  }
}
```

### 合规检查脚本

```python
# .cataforge/runtime/conformance.py
"""平台合规检查。"""
from .profile_loader import load_profile
from .types import CAPABILITY_IDS


REQUIRED_CAPABILITIES = [
    "file_read", "file_write", "file_edit", "file_glob",
    "file_grep", "shell_exec", "agent_dispatch",
]


def check_conformance(platform_id: str) -> list[str]:
    issues = []

    try:
        profile = load_profile(platform_id)
    except Exception as e:
        return [f"FAIL: 无法加载 {platform_id} profile: {e}"]

    if profile.get("platform_id") != platform_id:
        issues.append(f"FAIL: platform_id 不匹配")

    tool_map = profile.get("tool_map", {})
    for cap in REQUIRED_CAPABILITIES:
        if cap not in tool_map or tool_map[cap] is None:
            issues.append(f"WARN: {platform_id} 未映射必需能力 {cap}")

    if "dispatch" not in profile:
        issues.append(f"FAIL: 缺少 dispatch 配置")

    if "hooks" not in profile:
        issues.append(f"FAIL: 缺少 hooks 配置")

    return issues
```

### migration_checks 更新

`.cataforge/framework.json` 新增检查项：

```json
{
  "id": "mc-0.10.0-cataforge-dir",
  "release_version": "0.10.0",
  "description": ".cataforge/ 目录必须存在且包含核心文件",
  "type": "dir_must_contain_files",
  "path": ".cataforge",
  "patterns": [
    "framework.json",
    "PROJECT-STATE.md",
    "platforms/claude-code/profile.yaml",
    "runtime/__init__.py",
    "hooks/hooks.yaml"
  ]
},
{
  "id": "mc-0.10.0-override-mechanism",
  "release_version": "0.10.0",
  "description": "dispatch-prompt.md 必须包含 OVERRIDE 标记",
  "type": "file_must_contain",
  "path": ".cataforge/skills/agent-dispatch/templates/dispatch-prompt.md",
  "patterns": ["OVERRIDE:dispatch_syntax", "OVERRIDE:return_format"]
},
{
  "id": "mc-0.10.0-capability-ids",
  "release_version": "0.10.0",
  "description": "源 AGENT.md 必须使用能力标识符",
  "type": "file_must_not_contain",
  "path": ".cataforge/agents/orchestrator/AGENT.md",
  "patterns": ["tools: Read"]
}
```

### 版本号升级

```toml
# pyproject.toml
version = "0.10.0"
```

---

## 验收标准


| #      | 标准                                            | 验证方式    |
| ------ | --------------------------------------------- | ------- |
| AC-5.1 | `pytest tests/test_runtime/` 全部通过             | CI 运行   |
| AC-5.2 | `conformance.py --platform claude-code` 返回 0  | CLI     |
| AC-5.3 | `conformance.py --platform cursor` 返回 0       | CLI     |
| AC-5.4 | Bootstrap 时提供平台选择步骤                           | 人工验证    |
| AC-5.5 | framework.json 含 `runtime_api_version: "1.0"` | JSON 检查 |
| AC-5.6 | migration_checks 含 3 个新检查项                    | JSON 检查 |
| AC-5.7 | `deploy --platform all` 对 4 个平台均不报错           | CLI 运行  |
| AC-5.8 | ORCHESTRATOR-PROTOCOLS.md 含平台选择步骤             | grep 验证 |


---

## 风险项


| 风险                        | 影响                   | 缓解                                            |
| ------------------------- | -------------------- | --------------------------------------------- |
| `requires-python >= 3.10` | `X | None` 语法需 3.10+ | 所有模块已使用 `from __future__ import annotations`  |
| PyYAML 依赖                 | 测试需要 yaml 包          | `pyproject.toml` 的 dev dependencies 加入 pyyaml |
| Phase 5 依赖 Phase 1-4 全部完成 | 串行瓶颈                 | 测试用例提前编写（TDD），Phase 1-4 完成后直接运行               |


