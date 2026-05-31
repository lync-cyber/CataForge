# 插件

插件给框架扩展 skill / agent / hook / MCP server，无需改动框架本体。两种来源：

- **本地插件** —— `.cataforge/plugins/<id>/`，随仓库提交。
- **pip 插件** —— 声明 `cataforge.plugins` entry point 的已安装包。

## 布局

每个插件根目录有一个 `cataforge-plugin.yaml`，按需提供资产子目录：

```
<plugin>/
  cataforge-plugin.yaml
  skills/<skill-id>/SKILL.md
  agents/<agent-id>/AGENT.md
  mcp/<server-id>.yaml
```

manifest：

```yaml
id: my-plugin
name: My Plugin
version: 0.1.0
provides:
  skills: [greet]                # 解析 skills/greet/SKILL.md
  agents: [scribe]               # 解析 agents/scribe/AGENT.md
  mcp_servers: [my-srv]          # 解析 mcp/my-srv.yaml
  hooks:
    - event: PreToolUse          # 折叠进 hooks.yaml 事件表
      script: guard.py
      matcher_capability: shell_exec
requires:
  commands: [git]
  pip: [httpx]
```

`provides.{skills,agents,mcp_servers}` 是 id 列表，配合插件根 `source_path` 解析到对应文件。entry-point 插件的工厂把 `source_path` 设为 `importlib.resources.files(pkg) / "cataforge_assets"`，包内按上面同样布局放资产。

## 优先级

同 id 冲突时，**先发现者胜**（entry-point 在本地插件之前）。资产解析的整体优先级：

```
overrides/user > overrides/project > .cataforge/（发货层） > 插件 > 包内 builtin
```

即插件位于发货层**之下**：框架自带的同 id agent/skill 覆盖插件版本。插件主要用于**新增** id。

## 消费面

| 资产 | 运行期 | 部署期 |
|------|--------|--------|
| skills | `SkillLoader`（`skill list` / `skill run`，沿用 builtin 脚本回退） | resolver 落地到 IDE skill 树 |
| agents | — | resolver 落地（section 补丁语义保留） |
| hooks | `bridge.generate_platform_hooks` 折叠进事件表 | 随 hook 部署 |
| mcp_servers | `MCPRegistry`（过同一条 untrusted-command 闸） | `deploy` 的 MCP 落地 |

## CLI

```bash
cataforge plugin list                          # 列出已发现插件
cataforge plugin install ./path/to/plugin      # 本地目录 → 拷入 .cataforge/plugins/<id>/
cataforge plugin install some-pip-package      # pip 包 → pip install
cataforge plugin remove <id-or-package>        # 本地删目录 / pip 卸载
```

本地安装认 `<source>/cataforge-plugin.yaml`；已存在需 `--force` 覆写。装/删后跑 `cataforge deploy` 让资产落地或清除。
