# Phase 4: 端到端验证与 API 稳定化 — 详细执行计划

> 前置条件: Phase 0-3 全部完成
> 预计工时: 1 周
> 目标: 确保运行时抽象层稳定可靠，锁定 API 版本

---

## 目标

1. 建立完整的测试套件覆盖 runtime 包
2. 改造 Bootstrap 流程支持平台选择
3. 审查 ORCHESTRATOR-PROTOCOLS.md 中的平台相关描述
4. 锁定 `runtime_api_version: 1.0`
5. 版本号升级

---

## Step 4.1: 测试套件

### 新增: `tests/test_runtime/__init__.py`

空文件。

### 新增: `tests/test_runtime/test_types.py`

```python
"""测试 runtime 类型定义。"""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".claude"))

from runtime.types import AgentStatus, DispatchRequest, AgentResult, Capability


class TestAgentStatus:
    def test_all_statuses_have_string_value(self):
        for status in AgentStatus:
            assert isinstance(status.value, str)

    def test_valid_statuses_match_schema(self):
        expected = {
            "completed", "needs_input", "blocked", "approved",
            "approved_with_notes", "needs_revision", "rolled-back",
        }
        actual = {s.value for s in AgentStatus}
        assert actual == expected


class TestDispatchRequest:
    def test_minimal_creation(self):
        req = DispatchRequest(
            agent_id="architect",
            task="设计系统架构",
            task_type="new_creation",
            input_docs=["docs/prd/prd-v1.md"],
            expected_output="docs/arch/arch-v1.md",
            phase="architecture",
            project_name="test-project",
        )
        assert req.agent_id == "architect"
        assert req.background is False
        assert req.max_turns is None

    def test_continuation_fields(self):
        req = DispatchRequest(
            agent_id="architect",
            task="继续设计",
            task_type="continuation",
            input_docs=[],
            expected_output="",
            phase="architecture",
            project_name="test",
            answers={"Q1": "A"},
            resume_guidance="从 Step 4 恢复",
        )
        assert req.answers == {"Q1": "A"}


class TestCapability:
    def test_all_capabilities_are_snake_case(self):
        caps = [
            Capability.FILE_READ, Capability.FILE_WRITE,
            Capability.FILE_EDIT, Capability.FILE_GLOB,
            Capability.FILE_GREP, Capability.SHELL_EXEC,
            Capability.WEB_SEARCH, Capability.WEB_FETCH,
            Capability.USER_QUESTION, Capability.AGENT_DISPATCH,
        ]
        for cap in caps:
            assert cap == cap.lower()
            assert "_" in cap
```

### 新增: `tests/test_runtime/test_result_parser.py`

```python
"""测试 4 级容错解析器。"""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".claude"))

from runtime.result_parser import parse_agent_result
from runtime.types import AgentStatus


class TestLevel1NormalParse:
    def test_complete_result(self):
        raw = """
        <agent-result>
        <status>completed</status>
        <outputs>docs/arch/arch-v1.md</outputs>
        <summary>架构设计完成</summary>
        </agent-result>
        """
        result = parse_agent_result(raw)
        assert result.status == AgentStatus.COMPLETED
        assert result.outputs == ["docs/arch/arch-v1.md"]
        assert "架构设计完成" in result.summary

    def test_needs_input_with_questions(self):
        raw = """
        <agent-result>
        <status>needs_input</status>
        <outputs>docs/arch/arch-v1.md</outputs>
        <summary>需要确认数据库选型</summary>
        </agent-result>
        <questions>[{"id":"Q1","text":"数据库选型"}]</questions>
        <completed-steps>Step 1, Step 2</completed-steps>
        <resume-guidance>从 Step 3 恢复</resume-guidance>
        """
        result = parse_agent_result(raw)
        assert result.status == AgentStatus.NEEDS_INPUT

    def test_multiple_outputs(self):
        raw = """
        <agent-result>
        <status>completed</status>
        <outputs>src/app.py, tests/test_app.py</outputs>
        <summary>实现完成</summary>
        </agent-result>
        """
        result = parse_agent_result(raw)
        assert len(result.outputs) == 2


class TestLevel2MissingTag:
    def test_no_tag_with_doc_type(self):
        result = parse_agent_result(
            "一些普通文本，没有 agent-result 标签",
            doc_type="arch",
        )
        # 应该尝试 Glob 推断或返回 blocked
        assert result.status in (AgentStatus.COMPLETED, AgentStatus.BLOCKED)

    def test_no_tag_no_doc_type(self):
        result = parse_agent_result("纯文本，无标签")
        assert result.status == AgentStatus.BLOCKED


class TestLevel3IncompleteFields:
    def test_missing_status_with_outputs(self):
        raw = """
        <agent-result>
        <outputs>docs/arch/arch-v1.md</outputs>
        <summary>完成</summary>
        </agent-result>
        """
        result = parse_agent_result(raw)
        assert result.status == AgentStatus.COMPLETED  # 有 outputs → 默认 completed

    def test_missing_outputs(self):
        raw = """
        <agent-result>
        <status>completed</status>
        <summary>完成</summary>
        </agent-result>
        """
        result = parse_agent_result(raw)
        assert result.status == AgentStatus.COMPLETED


class TestLevel4Truncation:
    def test_truncated_no_closing_tag(self):
        raw = """
        <agent-result>
        <status>completed</status>
        <outputs>docs/arch/arch-v1.md</outputs>
        """  # 无 </agent-result>
        result = parse_agent_result(raw)
        # 截断处理: 检查 git status 或返回 blocked
        assert result.status in (AgentStatus.NEEDS_INPUT, AgentStatus.BLOCKED)
```

### 新增: `tests/test_runtime/test_tool_map.py`

```python
"""测试工具映射表。"""
import yaml
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".claude"))

TOOL_MAP_PATH = Path(__file__).resolve().parents[2] / ".claude" / "runtime" / "tool_map.yaml"

REQUIRED_CAPABILITIES = [
    "file_read", "file_write", "file_edit", "file_glob", "file_grep",
    "shell_exec", "web_search", "web_fetch", "user_question", "agent_dispatch",
]

REQUIRED_PLATFORMS = ["claude-code", "cursor", "codex", "opencode"]


@pytest.fixture
def tool_map():
    with open(TOOL_MAP_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestToolMap:
    def test_all_platforms_present(self, tool_map):
        for platform in REQUIRED_PLATFORMS:
            assert platform in tool_map, f"Missing platform: {platform}"

    def test_all_capabilities_defined(self, tool_map):
        for platform in REQUIRED_PLATFORMS:
            for cap in REQUIRED_CAPABILITIES:
                assert cap in tool_map[platform], \
                    f"Missing capability {cap} for {platform}"

    def test_claude_code_tool_names(self, tool_map):
        cc = tool_map["claude-code"]
        assert cc["file_read"] == "Read"
        assert cc["shell_exec"] == "Bash"
        assert cc["agent_dispatch"] == "Agent"

    def test_cursor_tool_names_corrected(self, tool_map):
        """验证 Cursor 映射已基于实际 API 纠正。"""
        cur = tool_map["cursor"]
        assert cur["file_edit"] == "StrReplace"  # 非 Write
        assert cur["file_glob"] == "Glob"         # 非 Read
        assert cur["file_grep"] == "Grep"         # 非 Read
        assert cur["shell_exec"] == "Shell"       # 非 Bash
        assert cur["agent_dispatch"] == "Task"    # 非 Agent

    def test_codex_dispatch_is_spawn_agent(self, tool_map):
        assert tool_map["codex"]["agent_dispatch"] == "spawn_agent"
```

### 新增: `tests/test_runtime/test_registry.py`

```python
"""测试平台注册表。"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".claude"))

from runtime.adapters._registry import detect_platform, get_platform_display_name


class TestDetectPlatform:
    def test_default_is_claude_code(self):
        mock_json = json.dumps({"runtime": {"platform": "claude-code"}})
        with patch("builtins.open", mock_open(read_data=mock_json)):
            assert detect_platform() == "claude-code"

    def test_cursor_platform(self):
        mock_json = json.dumps({"runtime": {"platform": "cursor"}})
        with patch("builtins.open", mock_open(read_data=mock_json)):
            assert detect_platform() == "cursor"

    def test_missing_runtime_defaults_claude(self):
        mock_json = json.dumps({"version": "0.3.0"})
        with patch("builtins.open", mock_open(read_data=mock_json)):
            assert detect_platform() == "claude-code"

    def test_missing_file_defaults_claude(self):
        with patch("builtins.open", side_effect=OSError):
            assert detect_platform() == "claude-code"


class TestDisplayName:
    def test_known_platforms(self):
        assert get_platform_display_name("claude-code") == "Claude Code"
        assert get_platform_display_name("cursor") == "Cursor"
        assert get_platform_display_name("codex") == "Codex CLI"
        assert get_platform_display_name("opencode") == "OpenCode"
```

### 新增: `tests/test_runtime/test_claude_code_adapter.py`

```python
"""测试 Claude Code 适配器。"""
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".claude"))

from runtime.adapters.claude_code import ClaudeCodeDispatcher
from runtime.types import DispatchRequest


class TestClaudeCodeDispatcher:
    def test_platform_id(self):
        d = ClaudeCodeDispatcher()
        assert d.platform_id() == "claude-code"

    def test_dispatch_raises_not_implemented(self):
        d = ClaudeCodeDispatcher()
        req = DispatchRequest(
            agent_id="architect", task="test", task_type="new_creation",
            input_docs=[], expected_output="", phase="test", project_name="test",
        )
        with pytest.raises(NotImplementedError):
            d.dispatch(req)
```

---

## Step 4.2: Bootstrap 平台选择

### 修改: `.cataforge/scripts/framework/setup.py`

添加 `--platform` 参数，在 Bootstrap 时写入 `framework.json`：

```python
# 新增到 setup.py 的 argparse 中
parser.add_argument(
    "--platform",
    choices=["claude-code", "cursor", "codex", "opencode"],
    default=None,
    help="设置运行时平台标识（写入 framework.json runtime.platform）",
)
```

当 `--platform` 提供时：
1. 读取 framework.json
2. 设置 `runtime.platform` 字段
3. 写回 framework.json

### 修改: `ORCHESTRATOR-PROTOCOLS.md` §Bootstrap

在 Step 1（收集项目信息）之后、Step 2（选择执行模式）之前，插入：

```markdown
1.5. **确认运行时平台** — 自动检测当前运行环境，通过 AskUserQuestion 确认:
     - 选项: claude-code（默认）| cursor | codex | opencode
     - 结果写入 `framework.json` 的 `runtime.platform` 字段
     - 运行: `python .cataforge/scripts/framework/setup.py --platform {选择}`
```

### 修改: `ORCHESTRATOR-PROTOCOLS.md` 平台相关描述审查

需审查的段落：
1. Bootstrap Step 6: `--apply-permissions` 生成 Claude Code 专用 `Bash(...)` 格式 → 添加注释说明跨平台时由适配器生成对应权限配置
2. 所有 `python .cataforge/scripts/framework/event_logger.py` 的 Bash 命令 → 保持不变（event_logger 是框架内部脚本，通过 shell 执行与平台调度无关）
3. `git checkout --` 命令 → 保持不变（git 命令跨平台一致）

---

## Step 4.3: API 版本锁定与发布

### 修改: `.cataforge/framework.json`

确认 `runtime_api_version: "1.0"` 已在 Phase 1.2 写入。

### 新增: `.cataforge/runtime/adapters/_conformance.py`

```python
"""适配器合规性检查脚本。

验证一个适配器是否正确实现了所有必需接口。
可通过 CLI 运行: python -m runtime.adapters._conformance --platform cursor
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from runtime.interfaces import AgentDispatcher
from runtime.adapters._registry import get_dispatcher, get_tool_name_resolver
from runtime.types import Capability


REQUIRED_CAPABILITIES = [
    Capability.FILE_READ, Capability.FILE_WRITE, Capability.FILE_EDIT,
    Capability.FILE_GLOB, Capability.FILE_GREP, Capability.SHELL_EXEC,
    Capability.AGENT_DISPATCH,
]


def check_conformance(platform_id: str) -> list[str]:
    """检查指定平台适配器的合规性。

    Returns:
        问题列表（空列表表示合规）。
    """
    issues = []

    # 1. 适配器可实例化
    try:
        dispatcher = get_dispatcher(platform_id)
    except Exception as e:
        issues.append(f"FAIL: 无法创建 {platform_id} 适配器: {e}")
        return issues

    # 2. 实现了 AgentDispatcher 接口
    if not isinstance(dispatcher, AgentDispatcher):
        issues.append(f"FAIL: {platform_id} 适配器未实现 AgentDispatcher")

    # 3. platform_id 正确
    if dispatcher.platform_id() != platform_id:
        issues.append(f"FAIL: platform_id() 返回 '{dispatcher.platform_id()}'，期望 '{platform_id}'")

    # 4. 工具名解析覆盖必需能力
    resolver = get_tool_name_resolver(platform_id)
    for cap in REQUIRED_CAPABILITIES:
        name = resolver.resolve(cap)
        if name is None:
            issues.append(f"WARN: {platform_id} 未映射能力 {cap}")

    return issues


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CataForge 适配器合规检查")
    parser.add_argument("--platform", required=True)
    args = parser.parse_args()

    issues = check_conformance(args.platform)
    if issues:
        for issue in issues:
            print(issue)
        sys.exit(1)
    else:
        print(f"✓ {args.platform} 适配器合规检查通过")
        sys.exit(0)
```

### 修改: `pyproject.toml`

```toml
# 版本升级 (MINOR bump: 新功能)
version = "0.10.0"
```

同时确认 `requires-python = ">=3.11"`（types.py 使用了 `X | None` 语法）或提供 `from __future__ import annotations`。

### 修改: `CLAUDE.md`

更新 §框架机制 段落，反映跨平台能力的增加。

---

## Step 4.4: migration_checks 更新

### 修改: `.cataforge/framework.json` — migration_checks 数组

新增检查项：

```json
{
  "id": "mc-0.10.0-runtime-package",
  "release_version": "0.10.0",
  "description": "跨平台运行时包必须存在",
  "type": "dir_must_contain_files",
  "path": ".cataforge/runtime",
  "patterns": [
    "__init__.py",
    "types.py",
    "interfaces.py",
    "result_parser.py",
    "tool_map.yaml"
  ]
},
{
  "id": "mc-0.10.0-runtime-config",
  "release_version": "0.10.0",
  "description": "framework.json 必须包含 runtime 配置",
  "type": "file_must_contain",
  "path": ".cataforge/framework.json",
  "patterns": ["runtime_api_version", "runtime"]
},
{
  "id": "mc-0.10.0-no-hardcoded-agent-tool",
  "release_version": "0.10.0",
  "description": "agent-dispatch SKILL.md 不应包含 Claude Code 专用调度描述",
  "type": "file_must_not_contain",
  "path": ".cataforge/skills/agent-dispatch/SKILL.md",
  "patterns": ["claude-code 实现", "Agent tool:"]
},
{
  "id": "mc-0.10.0-capability-identifiers",
  "release_version": "0.10.0",
  "description": "AGENT.md frontmatter 应使用能力标识符而非平台工具名",
  "type": "file_must_not_contain",
  "path": ".cataforge/agents/orchestrator/AGENT.md",
  "patterns": ["tools: Read"]
}
```

---

## 验收标准

| # | 标准 | 验证方式 |
|---|------|---------|
| AC-4.1 | `pytest tests/test_runtime/` 全部通过 | CI 运行 |
| AC-4.2 | `_conformance.py --platform claude-code` 返回 0 | CLI 运行 |
| AC-4.3 | Bootstrap 时提供平台选择步骤 | 人工验证 |
| AC-4.4 | `framework.json` 含 `runtime_api_version: "1.0"` | JSON 检查 |
| AC-4.5 | `pyproject.toml` 版本升级为 `0.10.0` | 读取确认 |
| AC-4.6 | `migration_checks` 含 4 个新检查项 | JSON 检查 |
| AC-4.7 | ORCHESTRATOR-PROTOCOLS.md 含平台选择步骤 | grep 验证 |

---

## 风险项

| 风险 | 影响 | 缓解方案 |
|------|------|---------|
| `requires-python >= 3.11` 与部分环境不兼容 | types.py 的 `X \| None` 语法需 3.10+ | 所有模块添加 `from __future__ import annotations` 以支持 3.8+ |
| PyYAML 依赖 | test_tool_map.py 需要 yaml 包 | 在 pyproject.toml 添加 `[project.optional-dependencies] dev = ["pyyaml", "pytest"]` |
| Phase 4 依赖 Phase 1-3 全部完成 | 串行瓶颈 | 测试用例可提前编写（TDD 风格），Phase 1-3 完成后直接运行 |
