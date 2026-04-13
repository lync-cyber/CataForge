# Phase 1: 最小抽象提取 — 详细执行计划

> 前置条件: Phase 0 完成（`.cataforge/` 目录结构已建立）
> 预计工时: 1-2 周
> 决策依据: ROADMAP.md §设计决策记录
> 路径约定: 所有框架文件路径以 `.cataforge/` 为前缀

---

## 目标

1. 建立 `.cataforge/runtime/` Python 包，定义平台无关的调度接口和数据类型
2. 实现 Claude Code 身份适配器（包装现有行为）
3. 将 `agent-dispatch/SKILL.md` 和 `tdd-engine/SKILL.md` 中的平台专用描述替换为平台无关描述
4. 将所有 AGENT.md frontmatter 中的工具名迁移为能力标识符
5. 从 SKILL.md 提取 `result_parser` 为 Python 模块

---

## Step 1.1: 建立 runtime 包骨架

### 新增: `.cataforge/runtime/__init__.py`

```python
"""CataForge Cross-Platform Runtime — 调度抽象层。

提供平台无关的 Agent 调度接口，由各平台适配器实现具体翻译。
"""
from .types import AgentStatus, AgentResult, DispatchRequest
from .interfaces import AgentDispatcher, AgentDefinitionAdapter
from .result_parser import parse_agent_result

__all__ = [
    "AgentStatus",
    "AgentResult",
    "DispatchRequest",
    "AgentDispatcher",
    "AgentDefinitionAdapter",
    "parse_agent_result",
]
```

### 新增: `.cataforge/runtime/types.py`

```python
"""平台无关的数据类型定义。"""
from dataclasses import dataclass, field
from enum import Enum


class AgentStatus(Enum):
    COMPLETED = "completed"
    NEEDS_INPUT = "needs_input"
    BLOCKED = "blocked"
    APPROVED = "approved"
    APPROVED_WITH_NOTES = "approved_with_notes"
    NEEDS_REVISION = "needs_revision"
    ROLLED_BACK = "rolled-back"


@dataclass
class DispatchRequest:
    """平台无关的调度请求 — 由 orchestrator 构建。"""
    agent_id: str
    task: str
    task_type: str  # new_creation | revision | continuation | ...
    input_docs: list[str]
    expected_output: str
    phase: str
    project_name: str
    background: bool = False
    max_turns: int | None = None
    review_path: str | None = None
    answers: dict | None = None
    intermediate_outputs: list[str] | None = None
    resume_guidance: str | None = None
    change_analysis: str | None = None


@dataclass
class AgentResult:
    """平台无关的返回值 — 由适配器从平台输出解析。"""
    status: AgentStatus
    outputs: list[str]
    summary: str
    questions: list[dict] | None = None
    completed_steps: str | None = None
    resume_guidance: str | None = None


# 能力标识符常量（AGENT.md frontmatter 中使用）
class Capability:
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_EDIT = "file_edit"
    FILE_GLOB = "file_glob"
    FILE_GREP = "file_grep"
    SHELL_EXEC = "shell_exec"
    WEB_SEARCH = "web_search"
    WEB_FETCH = "web_fetch"
    USER_QUESTION = "user_question"
    AGENT_DISPATCH = "agent_dispatch"
```

### 新增: `.cataforge/runtime/interfaces.py`

```python
"""平台无关的抽象接口定义。"""
from abc import ABC, abstractmethod
from .types import DispatchRequest, AgentResult


class AgentDispatcher(ABC):
    @abstractmethod
    def dispatch(self, request: DispatchRequest) -> AgentResult:
        """分派任务给子代理。适配器负责：
        1. 构建平台专属 prompt（使用 PromptBuilder）
        2. 调用平台调度工具
        3. 解析返回值为 AgentResult
        """
        ...

    @abstractmethod
    def platform_id(self) -> str:
        """返回平台标识: claude-code | cursor | codex | opencode"""
        ...


class AgentDefinitionAdapter(ABC):
    @abstractmethod
    def load(self, agent_id: str):
        """从平台原生格式加载 Agent 定义。"""
        ...

    @abstractmethod
    def sync_from_canonical(self, canonical_dir: str) -> None:
        """从规范目录同步到平台目录。"""
        ...


class HookBridge(ABC):
    @abstractmethod
    def translate_config(self, cataforge_hooks: dict) -> dict:
        """将 CataForge Hook 配置翻译为平台格式。"""
        ...

    @abstractmethod
    def get_supported_events(self) -> list[str]:
        """当前平台支持的事件列表。"""
        ...


class InstructionFileSync(ABC):
    @abstractmethod
    def sync(self, claude_md_path: str) -> None:
        """将 CLAUDE.md 内容同步到平台指令文件。"""
        ...


class ToolNameResolver:
    """能力标识符 → 平台工具名的解析器。"""

    def __init__(self, platform_id: str, tool_map: dict):
        self._platform_id = platform_id
        self._map = tool_map.get(platform_id, {})

    def resolve(self, capability: str) -> str | None:
        """将能力标识符翻译为当前平台的工具名。
        返回 None 表示当前平台不支持该能力。"""
        return self._map.get(capability)

    def resolve_many(self, capabilities: list[str]) -> list[str]:
        """批量翻译，跳过不支持的能力。"""
        return [name for cap in capabilities
                if (name := self.resolve(cap)) is not None]
```

### 新增: `.cataforge/runtime/tool_map.yaml`

基于决策 D-4 纠正 v2 方案中 Cursor 的错误映射：

```yaml
# 能力标识符 → 平台工具名映射
# 能力标识符使用 snake_case，是 AGENT.md frontmatter 中的规范值
# null 表示平台不支持该能力

claude-code:
  file_read: Read
  file_write: Write
  file_edit: Edit
  file_glob: Glob
  file_grep: Grep
  shell_exec: Bash
  web_search: WebSearch
  web_fetch: WebFetch
  user_question: AskUserQuestion
  agent_dispatch: Agent

cursor:
  file_read: Read
  file_write: Write
  file_edit: StrReplace   # Cursor 有独立的 StrReplace 工具（非 Write）
  file_glob: Glob          # Cursor 有独立的 Glob 工具
  file_grep: Grep          # Cursor 有独立的 Grep 工具
  shell_exec: Shell        # Cursor 用 Shell（非 Bash）
  web_search: WebSearch
  web_fetch: WebFetch
  user_question: null      # Chat 替代
  agent_dispatch: Task     # Cursor 用 Task（非 Agent）

codex:
  file_read: shell         # 通过 shell cat
  file_write: apply_patch
  file_edit: apply_patch
  file_glob: shell         # 通过 shell find
  file_grep: shell         # 通过 shell grep
  shell_exec: shell
  web_search: web_search
  web_fetch: shell         # 通过 shell curl
  user_question: null      # 无（异步线程模式）
  agent_dispatch: spawn_agent

opencode:
  file_read: read
  file_write: write
  file_edit: edit
  file_glob: glob
  file_grep: grep
  shell_exec: bash
  web_search: websearch
  web_fetch: webfetch
  user_question: question
  agent_dispatch: task
```

### 新增: `.cataforge/runtime/adapters/__init__.py`

```python
"""Platform adapters package."""
```

### 新增: `.cataforge/runtime/adapters/_registry.py`

```python
"""平台检测与适配器工厂。"""
import json
import os
from pathlib import Path

import yaml

from ..interfaces import AgentDispatcher, ToolNameResolver


_FRAMEWORK_JSON = os.path.join(
    os.path.dirname(__file__), "..", "..", "framework.json"
)
_TOOL_MAP_YAML = os.path.join(os.path.dirname(__file__), "..", "tool_map.yaml")


def detect_platform() -> str:
    """从 framework.json 读取 runtime.platform，缺省返回 'claude-code'。"""
    try:
        with open(_FRAMEWORK_JSON, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config.get("runtime", {}).get("platform", "claude-code")
    except (OSError, json.JSONDecodeError):
        return "claude-code"


def load_tool_map() -> dict:
    """加载 tool_map.yaml。"""
    with open(_TOOL_MAP_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_tool_name_resolver(platform_id: str | None = None) -> ToolNameResolver:
    """获取当前平台的工具名解析器。"""
    pid = platform_id or detect_platform()
    return ToolNameResolver(pid, load_tool_map())


def get_dispatcher(platform_id: str | None = None) -> AgentDispatcher:
    """获取当前平台的调度适配器实例。"""
    pid = platform_id or detect_platform()

    if pid == "claude-code":
        from .claude_code import ClaudeCodeDispatcher
        return ClaudeCodeDispatcher()
    elif pid == "cursor":
        from .cursor import CursorDispatcher
        return CursorDispatcher()
    elif pid == "codex":
        from .codex import CodexDispatcher
        return CodexDispatcher()
    elif pid == "opencode":
        from .opencode import OpenCodeDispatcher
        return OpenCodeDispatcher()
    else:
        raise ValueError(f"Unknown platform: {pid}")


def get_platform_display_name(platform_id: str | None = None) -> str:
    """获取平台的用户可读显示名。"""
    names = {
        "claude-code": "Claude Code",
        "cursor": "Cursor",
        "codex": "Codex CLI",
        "opencode": "OpenCode",
    }
    pid = platform_id or detect_platform()
    return names.get(pid, pid)
```

### 新增: `.cataforge/runtime/adapters/claude_code.py`

```python
"""Claude Code 适配器 — 身份适配，包装现有 Agent tool 行为。

这是从 agent-dispatch/SKILL.md §claude-code 实现 提取的逻辑。
Claude Code 使用 Agent tool 启动独立子代理，必须指定 subagent_type 参数。
"""
from ..interfaces import AgentDispatcher
from ..types import DispatchRequest, AgentResult
from ..result_parser import parse_agent_result


class ClaudeCodeDispatcher(AgentDispatcher):
    def dispatch(self, request: DispatchRequest) -> AgentResult:
        """构建 Claude Code Agent tool 调用。

        在实际 LLM 运行时中，此方法不会被 Python 直接调用——
        它描述的是 orchestrator 应构建的 Agent tool 调用格式。
        实际调度由 orchestrator 的 agent-dispatch skill 通过
        prompt 模板驱动 LLM 发起 Agent tool call。

        此类的作用是：
        1. 作为 Claude Code 平台调度行为的规范文档
        2. 为 result_parser 提供入口
        3. 为未来 Python-native 调度提供接口基础
        """
        raise NotImplementedError(
            "ClaudeCodeDispatcher.dispatch() 不直接执行调度。"
            "实际调度通过 agent-dispatch skill 的 prompt 模板驱动。"
            "本适配器用于平台标识、工具名解析和结果解析。"
        )

    def platform_id(self) -> str:
        return "claude-code"
```

---

## Step 1.2: framework.json 扩展

### 修改: `.cataforge/framework.json`

在顶层添加 `runtime` 对象和 `runtime_api_version` 字段：

**变更位置**: 第 1-3 行之后（`"version"` 和 `"description"` 之后）

```json
{
  "version": "0.3.0",
  "description": "...(现有描述)...",
  "runtime_api_version": "1.0",
  "runtime": {
    "platform": "claude-code",
    "adapter": "adapters.claude_code"
  },
  "upgrade": { ... }
}
```

**新增字段说明**:

- `runtime_api_version`: 运行时接口版本（独立于 framework schema 版本）
- `runtime.platform`: 当前活跃平台标识
- `runtime.adapter`: 适配器模块路径（相对于 `.cataforge/runtime/`）

---

## Step 1.3: result_parser 提取

### 新增: `.cataforge/runtime/result_parser.py`

从 `agent-dispatch/SKILL.md:46-60` 的自然语言容错规范提取为 Python 实现：

```python
"""Agent 返回值 4 级容错解析器。

规范来源: agent-dispatch/SKILL.md §返回值解析与容错
"""
import glob as glob_mod
import os
import re
import subprocess
from .types import AgentResult, AgentStatus


def parse_agent_result(
    raw_output: str,
    doc_type: str | None = None,
    docs_dir: str = "docs",
) -> AgentResult:
    """4 级容错解析 <agent-result> 返回值。

    Level 1: 正常 <agent-result> XML 解析
    Level 2: 标签缺失 → Glob docs/ 推断
    Level 3: 字段不完整 → 默认值填充
    Level 4: maxTurns 截断 → git status 检查
    """

    # Level 1: 正常解析
    ar_match = re.search(
        r"<agent-result>(.*?)</agent-result>", raw_output, re.DOTALL
    )
    if ar_match:
        content = ar_match.group(1)
        return _parse_xml_fields(content)

    # Level 4: maxTurns 截断（无结束标签）
    if "<agent-result>" in raw_output and "</agent-result>" not in raw_output:
        return _handle_truncation(raw_output, doc_type, docs_dir)

    # Level 2: 标签完全缺失
    return _handle_missing_tag(doc_type, docs_dir)


def _parse_xml_fields(content: str) -> AgentResult:
    """从 <agent-result> 内容解析字段。"""
    status_str = _extract_field(content, "status")
    outputs_str = _extract_field(content, "outputs")
    summary = _extract_field(content, "summary") or ""

    # Level 3: 字段不完整兜底
    status = _parse_status(status_str, bool(outputs_str))
    outputs = [p.strip() for p in outputs_str.split(",") if p.strip()] if outputs_str else []

    if not outputs:
        inferred = _glob_recent_docs("docs")
        if inferred:
            outputs = inferred

    questions = _extract_json_field(content, "questions")
    completed_steps = _extract_field(content, "completed-steps")
    resume_guidance = _extract_field(content, "resume-guidance")

    return AgentResult(
        status=status,
        outputs=outputs,
        summary=summary,
        questions=questions,
        completed_steps=completed_steps,
        resume_guidance=resume_guidance,
    )


def _parse_status(status_str: str | None, has_outputs: bool) -> AgentStatus:
    """解析 status 字符串为枚举值，缺失时按规则推断。"""
    if status_str:
        try:
            return AgentStatus(status_str.strip())
        except ValueError:
            pass
    # 缺 status → 默认 completed（如果有 outputs）
    return AgentStatus.COMPLETED if has_outputs else AgentStatus.BLOCKED


def _handle_truncation(
    raw_output: str, doc_type: str | None, docs_dir: str
) -> AgentResult:
    """处理 maxTurns 截断: 检查 git status 判断是否有部分产出。"""
    new_files = _git_status_new_files(docs_dir)
    if new_files and _has_substantive_content(new_files):
        return AgentResult(
            status=AgentStatus.NEEDS_INPUT,
            outputs=new_files,
            summary="子代理被截断但有部分产出，需以 continuation 模式恢复",
            resume_guidance="maxTurns 截断，从已有产出继续",
        )
    return AgentResult(
        status=AgentStatus.BLOCKED,
        outputs=[],
        summary="子代理被截断且无有效产出，需人工介入",
    )


def _handle_missing_tag(
    doc_type: str | None, docs_dir: str
) -> AgentResult:
    """处理完全无 <agent-result> 标签的情况。"""
    if doc_type:
        pattern = os.path.join(docs_dir, doc_type, "*")
        new_files = glob_mod.glob(pattern)
        if new_files:
            return AgentResult(
                status=AgentStatus.COMPLETED,
                outputs=new_files,
                summary="子代理未返回结构化结果，通过文件检测推断为完成",
            )
    return AgentResult(
        status=AgentStatus.BLOCKED,
        outputs=[],
        summary="子代理未返回结构化结果且无可检测产出",
    )


def _extract_field(content: str, tag: str) -> str | None:
    m = re.search(rf"<{tag}>\s*(.*?)\s*</{tag}>", content, re.DOTALL)
    return m.group(1).strip() if m else None


def _extract_json_field(content: str, tag: str) -> list | None:
    import json
    raw = _extract_field(content, tag)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


def _glob_recent_docs(docs_dir: str) -> list[str]:
    """扫描 docs/ 下最近修改的文件。"""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", docs_dir],
            capture_output=True, text=True, timeout=10,
        )
        return [
            line[3:].strip()
            for line in result.stdout.splitlines()
            if line.startswith("?") or line.startswith(" M") or line.startswith("A")
        ]
    except (subprocess.SubprocessError, FileNotFoundError):
        return []


def _git_status_new_files(docs_dir: str) -> list[str]:
    """通过 git status 获取新增/修改文件。"""
    return _glob_recent_docs(docs_dir)


def _has_substantive_content(file_paths: list[str]) -> bool:
    """检查文件是否含非空章节（至少一个 ## 标题下有实际内容）。"""
    for path in file_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            sections = re.split(r"^##\s+", content, flags=re.MULTILINE)
            for section in sections[1:]:  # 跳过标题前内容
                body = section.split("\n", 1)[-1].strip() if "\n" in section else ""
                if len(body) > 20:
                    return True
        except OSError:
            continue
    return False
```

---

## Step 1.4: agent-dispatch/SKILL.md 拆分

### 修改: `.cataforge/skills/agent-dispatch/SKILL.md`

以下是逐段变更说明：

#### 变更 1: frontmatter L5 — suggested-tools 能力标识符化

```
# 旧 (L5)
suggested-tools: Read, Glob, Grep, Bash, Agent

# 新
suggested-tools: file_read, file_glob, file_grep, shell_exec, agent_dispatch
```

#### 变更 2: L38-44 — 删除 `## claude-code 实现` 段落，替换为平台无关描述

```
# 旧 (L38-44)
## claude-code 实现 (默认)
使用 Claude Code 的 Agent tool 启动独立子代理，**必须指定 subagent_type 参数**。

完整 prompt 模板见: `.cataforge/skills/agent-dispatch/templates/dispatch-prompt.md`（含 COMMON-SECTIONS 共享段落）

> 修改 prompt 模板影响所有通过 agent-dispatch 调度的 Agent，请谨慎变更并做 diff review。
> TDD 子代理由 tdd-engine 直接调度，仅传入任务信息，通用约束和返回格式依赖 AGENT.md 自动加载，无需同步。

# 新
## 平台调度实现
调度通过当前运行时平台的调度工具执行，由 `.cataforge/runtime/adapters/` 中的适配器实现格式翻译。
当前平台由 `framework.json` 的 `runtime.platform` 字段决定。

| 平台 | 调度工具 | 适配器 |
|------|---------|--------|
| claude-code | Agent (subagent_type 参数) | `adapters/claude_code.py` |
| cursor | Task (subagent_type 参数) | `adapters/cursor.py` |
| codex | spawn_agent + wait_agent | `adapters/codex.py` |
| opencode | task (subagent_type 参数) | `adapters/opencode.py` |

完整 prompt 模板见: `.cataforge/skills/agent-dispatch/templates/dispatch-prompt.md`（含 COMMON-SECTIONS 共享段落）

> 修改 prompt 模板影响所有通过 agent-dispatch 调度的 Agent，请谨慎变更并做 diff review。
> TDD 子代理由 tdd-engine 直接调度，仅传入任务信息，通用约束和返回格式依赖 AGENT.md 自动加载，无需同步。
```

#### 变更 3: L46-60 — 添加 Python 实现引用

在 `## 返回值解析与容错` 段落开头（L47 之后）插入：

```markdown
> Python 实现: `.cataforge/runtime/result_parser.py`（`parse_agent_result()` 函数实现以下 4 级容错）
```

#### 变更 4: L68-73 — 注意事项平台无关化

```
# 旧 (L71)
- **子代理无法使用Agent tool** — TDD子代理由orchestrator直接通过tdd-engine skill启动

# 新
- **子代理无法使用调度工具** — TDD子代理由orchestrator直接通过tdd-engine skill启动
```

#### 变更 5: L74-75 — 运行时支持更新

```
# 旧
## 运行时支持
当前版本仅支持 claude-code runtime。其他运行时（Cursor、Codex 等）为规划中功能。

# 新
## 运行时支持
支持平台: claude-code（默认）| cursor | codex | opencode
当前平台由 `framework.json` 的 `runtime.platform` 字段控制。
平台适配器: `.cataforge/runtime/adapters/`
工具名映射: `.cataforge/runtime/tool_map.yaml`
```

---

## Step 1.5: tdd-engine/SKILL.md 平台无关化

### 修改: `.cataforge/skills/tdd-engine/SKILL.md`

#### 变更 1: frontmatter L5

```
# 旧
suggested-tools: Read, Write, Edit, Bash, Glob, Grep, Agent

# 新
suggested-tools: file_read, file_write, file_edit, shell_exec, file_glob, file_grep, agent_dispatch
```

#### 变更 2: L20-26 架构图

```
# 旧
orchestrator (主线程)
  ├─ 通过Agent tool启动 → RED SubAgent (test-writer) — 独立上下文
  ├─ 收集RED产出 → 通过Agent tool启动 → GREEN SubAgent (implementer) — 独立上下文
  ├─ 收集GREEN产出 → 通过Agent tool启动 → REFACTOR SubAgent (refactorer) — 独立上下文
  └─ 汇总产出 → 更新dev-plan任务状态

# 新
orchestrator (主线程)
  ├─ 通过调度接口启动 → RED SubAgent (test-writer) — 独立上下文
  ├─ 收集RED产出 → 通过调度接口启动 → GREEN SubAgent (implementer) — 独立上下文
  ├─ 收集GREEN产出 → 通过调度接口启动 → REFACTOR SubAgent (refactorer) — 独立上下文
  └─ 汇总产出 → 更新dev-plan任务状态
```

#### 变更 3: L78-93 — RED Phase 调度模板

```
# 旧 (L80-93)
Agent tool:
  subagent_type: "test-writer"
  description: "TDD RED: T-xxx 编写失败测试"
  prompt: |
    ...

# 新
调度请求:
  agent_id: "test-writer"
  description: "TDD RED: T-xxx 编写失败测试"
  prompt: |
    ...
```

（注意: 格式从 `Agent tool:` 变为 `调度请求:`，所有平台适配器理解此统一格式）

#### 变更 4: L103-118 — GREEN Phase 调度模板

同上格式变更: `Agent tool:` → `调度请求:`，`subagent_type:` → `agent_id:`

#### 变更 5: L125-139 — REFACTOR Phase 调度模板

同上格式变更。

#### 变更 6: L147-170 — Light 模式调度模板

同上格式变更: L148-149 的 `使用 Agent tool 启动:` → `使用调度接口启动:`
代码块内 `Agent tool:` → `调度请求:`

#### 总计变更点: 8 处（1 frontmatter + 1 架构图 + 4 调度模板 + 2 描述性文字）

---

## Step 1.6: 能力标识符迁移（13 个 AGENT.md）

### 映射表


| Claude Code 工具名   | 能力标识符            |
| ----------------- | ---------------- |
| `Read`            | `file_read`      |
| `Write`           | `file_write`     |
| `Edit`            | `file_edit`      |
| `Glob`            | `file_glob`      |
| `Grep`            | `file_grep`      |
| `Bash`            | `shell_exec`     |
| `WebSearch`       | `web_search`     |
| `WebFetch`        | `web_fetch`      |
| `AskUserQuestion` | `user_question`  |
| `Agent`           | `agent_dispatch` |


### 各 AGENT.md 变更清单


| AGENT.md          | 旧 `tools:`                                                                  | 新 `tools:`                                                                                                 | 旧 `disallowedTools:`                                | 新 `disallowedTools:`                                               |
| ----------------- | --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | --------------------------------------------------- | ------------------------------------------------------------------ |
| `orchestrator`    | `Read, Write, Edit, Glob, Grep, Bash, Agent, AskUserQuestion`               | `file_read, file_write, file_edit, file_glob, file_grep, shell_exec, agent_dispatch, user_question`        | `[]`                                                | `[]`                                                               |
| `architect`       | `Read, Write, Edit, Glob, Grep, Bash, WebSearch, WebFetch, AskUserQuestion` | `file_read, file_write, file_edit, file_glob, file_grep, shell_exec, web_search, web_fetch, user_question` | `Agent`                                             | `agent_dispatch`                                                   |
| `product-manager` | `Read, Write, Edit, Glob, Grep, WebSearch, WebFetch, AskUserQuestion`       | `file_read, file_write, file_edit, file_glob, file_grep, web_search, web_fetch, user_question`             | `Bash, Agent`                                       | `shell_exec, agent_dispatch`                                       |
| `ui-designer`     | `Read, Write, Edit, Glob, Grep, Bash, WebSearch, WebFetch, AskUserQuestion` | `file_read, file_write, file_edit, file_glob, file_grep, shell_exec, web_search, web_fetch, user_question` | `Agent`                                             | `agent_dispatch`                                                   |
| `tech-lead`       | `Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion`                      | `file_read, file_write, file_edit, file_glob, file_grep, shell_exec, user_question`                        | `Agent, WebSearch, WebFetch`                        | `agent_dispatch, web_search, web_fetch`                            |
| `implementer`     | `Read, Write, Edit, Glob, Grep, Bash`                                       | `file_read, file_write, file_edit, file_glob, file_grep, shell_exec`                                       | `Agent, WebSearch, WebFetch, AskUserQuestion`       | `agent_dispatch, web_search, web_fetch, user_question`             |
| `test-writer`     | `Read, Write, Edit, Glob, Grep, Bash`                                       | `file_read, file_write, file_edit, file_glob, file_grep, shell_exec`                                       | `Agent, WebSearch, WebFetch, AskUserQuestion`       | `agent_dispatch, web_search, web_fetch, user_question`             |
| `refactorer`      | `Read, Write, Edit, Glob, Grep, Bash`                                       | `file_read, file_write, file_edit, file_glob, file_grep, shell_exec`                                       | `Agent, WebSearch, WebFetch, AskUserQuestion`       | `agent_dispatch, web_search, web_fetch, user_question`             |
| `qa-engineer`     | `Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion`                      | `file_read, file_write, file_edit, file_glob, file_grep, shell_exec, user_question`                        | `Agent, WebSearch, WebFetch`                        | `agent_dispatch, web_search, web_fetch`                            |
| `reviewer`        | `Read, Write, Edit, Glob, Grep, Bash`                                       | `file_read, file_write, file_edit, file_glob, file_grep, shell_exec`                                       | `Agent`                                             | `agent_dispatch`                                                   |
| `debugger`        | `Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion`                      | `file_read, file_write, file_edit, file_glob, file_grep, shell_exec, user_question`                        | `Agent, WebSearch, WebFetch`                        | `agent_dispatch, web_search, web_fetch`                            |
| `devops`          | `Read, Write, Edit, Glob, Grep, Bash`                                       | `file_read, file_write, file_edit, file_glob, file_grep, shell_exec`                                       | `Agent, AskUserQuestion, WebSearch, WebFetch`       | `agent_dispatch, user_question, web_search, web_fetch`             |
| `reflector`       | `Read, Write, Edit, Glob, Grep`                                             | `file_read, file_write, file_edit, file_glob, file_grep`                                                   | `Agent, AskUserQuestion, Bash, WebSearch, WebFetch` | `agent_dispatch, user_question, shell_exec, web_search, web_fetch` |


### 其他 AGENT.md 内文变更

`orchestrator/AGENT.md` L22:

```
# 旧
- 你作为主线程Agent运行，可使用Agent tool启动子代理

# 新
- 你作为主线程Agent运行，可通过调度接口启动子代理
```

### dispatch-prompt.md 变更

L6:

```
# 旧
Agent tool:
  subagent_type: "{agent_id}"

# 新
调度请求:
  agent_id: "{agent_id}"
```

### CLAUDE.md 变更

L6:

```
# 旧
- 运行时: claude-code

# 新
- 运行时: claude-code (支持平台: claude-code | cursor | codex | opencode)
```

L74:

```
# 旧
- 运行时: claude-code（agent-dispatch 通过 Agent tool + subagent_type 调度）

# 新
- 运行时: 由 framework.json runtime.platform 决定（agent-dispatch 通过平台调度接口 + subagent_type/agent_id 调度）
```

---

## 验收标准 (AC)


| #    | 标准                                                            | 验证方式                                                                                       |
| ---- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| AC-1 | `.cataforge/runtime/` 包可正常 import                                | `python -c "from .claude.runtime import AgentStatus, DispatchRequest, parse_agent_result"` |
| AC-2 | `tool_map.yaml` 包含 4 个平台的完整映射                                 | YAML lint + 人工审查                                                                           |
| AC-3 | `result_parser.py` 覆盖 4 级容错                                   | 单元测试（Level 1-4 各至少 1 个用例）                                                                  |
| AC-4 | `_registry.py` 能正确检测 `framework.json` 中的平台并返回 Claude Code 适配器 | 单元测试                                                                                       |
| AC-5 | `agent-dispatch/SKILL.md` 不含 `Agent tool` 或 `claude-code 实现`  | `grep -c "Agent tool                                                                       |
| AC-6 | `tdd-engine/SKILL.md` 不含 `Agent tool:`                        | `grep -c "Agent tool:" SKILL.md` 返回 0                                                      |
| AC-7 | 所有 13 个 AGENT.md 的 `tools:` 和 `disallowedTools:` 仅含能力标识符      | `grep -P "tools:.*\b(Read                                                                  |
| AC-8 | `framework.json` 含 `runtime` 和 `runtime_api_version` 字段       | JSON schema 验证                                                                             |
| AC-9 | `dispatch-prompt.md` 不含 `Agent tool:`                         | grep 验证                                                                                    |


---

## 风险项


| 风险                                            | 影响                                 | 缓解方案                                                                                     |
| --------------------------------------------- | ---------------------------------- | ---------------------------------------------------------------------------------------- |
| AGENT.md frontmatter 能力标识符不被 Claude Code 原生识别 | Claude Code 的 `tools:` 字段可能只认原生工具名 | 需验证 Claude Code 是否能正确处理自定义 frontmatter 值；如不能，保留原生工具名并在 AGENT.md 中添加 `capabilities:` 并行字段 |
| `result_parser.py` 的 git 命令在非 git 环境中失败       | Level 2/4 容错降级                     | 添加 subprocess 超时和 fallback                                                               |
| `tool_map.yaml` 需要 PyYAML 依赖                  | 部分环境无 PyYAML                       | 提供 JSON fallback 格式或 `json.tool_map.json`                                                |


---

## 执行顺序建议

```
1.1 runtime 包骨架 ─────► 1.2 framework.json ─────► 1.3 result_parser
                                                          │
1.6 AGENT.md 能力标识符迁移 ◄── 1.4 agent-dispatch ◄──────┘
                                      │
                                 1.5 tdd-engine
```

Step 1.1-1.3 可并行。1.4-1.6 依赖 1.1 的类型定义和 1.3 的解析器。