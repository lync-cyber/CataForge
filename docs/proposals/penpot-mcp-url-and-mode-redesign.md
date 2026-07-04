# 提案：Penpot MCP 以 PENPOT_MCP_URL 为统一 endpoint 事实源 + 模式语义重构

> 状态：已实施。PENPOT_MCP_URL 统一为 MCP endpoint 事实源 + 模式语义重构已落地（deploy 时 endpoint 解析、自托管默认单用户模式等后续修复见 git 历史）。以代码为准，本文余下为历史设计记录。
> 范围：`cataforge.adapter.integrations.penpot`（config / mcp_spec / commands / doctor / client / 向导）、下游 MCP 分发 spec、`.env.example`、相关文档。
> 交付边界：本文为单 PR 的施工蓝图与验收标准；落地代码以 git diff 为准。

---

## 0. 诊断结论（本机实测铁证）

自托管 Penpot MCP 基础设施在本机实测 **100% 健康**：7 容器全 Up（含 penpot-mcp）、`penpotapp/mcp:2.16` 镜像就绪、frontend+backend 均带 `enable-mcp`、`POST localhost:9001/mcp/stream` 的 `initialize` 返回 `serverInfo`、`localhost:9001/mcp/ws` 返回 `426 Upgrade Required`（插件 WebSocket 反代就绪）、`tools/list` 返回 4 个工具（`execute_code` / `high_level_overview` / `penpot_api_info` / `export_shape`）。而 `localhost:4400/4401/4402` 全部不可达。

"不可用" = 两个**非故障 gap**：

1. **端口认知断层**：`4400/4401/4402` 是 npx Local MCP 端口；自托管下 penpot-mcp 容器无端口映射，唯一入口是 `9001/mcp/stream`。
2. **流程缺口**：(a) 下游未拿到正确且可配的 MCP URL；(b) 用户未在浏览器把 MCP 插件 Connect 上——`execute_code` 工具明写"in the Penpot plugin context"，工具执行依赖已连接的浏览器插件，而 `cmd_deploy` 从不引导这一步。

## 1. 现状缺陷

1. `PENPOT_MCP_URL` 代码库零引用——endpoint 不可配，无单一事实源。
2. `build_penpot_mcp_spec` 硬编码 url，下游分发与运行现实解耦（[mcp_spec.py](../../src/cataforge/adapter/integrations/penpot/mcp_spec.py)）。
3. 模式术语误用：`remote` 实为"SaaS 后端 + 本地 npx MCP"，与 Penpot 官方"Remote MCP（托管 endpoint + userToken）"不是一回事。
4. 自托管 `cmd_deploy` 无插件连接引导（对比 `cmd_remote` 有 `print_remote_onboarding`）。
5. 健康探测假阳性：`_is_mcp_running` 只验握手，握手 Up ≠ 插件已连 ≠ 能读设计。
6. npx 本地 MCP 链路脆弱（[patterns.py](../../src/cataforge/adapter/integrations/penpot/patterns.py) 已沉淀 4 类失败）。

## 2. 设计

### 2.1 PENPOT_MCP_URL 作为统一 endpoint 事实源

下游分发 spec 的 url 改为占位符：

```
${PENPOT_MCP_URL:-http://localhost:{penpot_port}/mcp/stream}
```

- spec（`.cataforge/mcp/penpot.yaml`，git-tracked）**不含明文 token**；token 随 `PENPOT_MCP_URL` 在 `.env`（gitignored）。
- deploy 把占位符**原样**注入 `.mcp.json`（gitignored），Claude Code 运行时展开（支持 `${VAR}` / `${VAR:-default}`，作用于 url/headers/env）。
- 自托管不设变量 → 回退本机；SaaS/远程设 `PENPOT_MCP_URL=https://<domain>/mcp/stream?userToken=KEY`。

安全约束（实测）：`.cataforge/mcp/*.yaml` git-tracked；`.mcp.json` / `.cursor/mcp.json` / `.env` gitignored。

### 2.2 模式语义重构 + 重命名

| 命令 | 模式 | MCP 运行 | endpoint | 状态 |
|------|------|---------|----------|------|
| `penpot remote` | 托管 | Penpot 托管 | `$PENPOT_MCP_URL` | 推荐 |
| `penpot deploy` | 自托管 | docker penpot-mcp 容器 + 浏览器插件 | `localhost:9001/mcp/stream` | 数据自管 |
| `penpot mcp-only` | npx | 宿主 npx + 浏览器插件 | `localhost:4401/mcp` | deprecated |

- `remote` 语义反转为**纯托管 URL**，不起任何本地进程：校验 `PENPOT_MCP_URL` → `register_claude_mcp` → 结束。
- 原"SaaS 后端 + 本地 npx"中间形态消解：托管用例归 `remote`，接已有实例的 npx 用例归 `mcp-only`（deprecated）。
- `mcp-only` 与 npx 链路保留功能但打 deprecation warning，引导迁移 `remote` / `deploy`。

### 2.3 自托管真正可用

- `cmd_deploy` 部署后新增 `print_self_hosted_onboarding`：引导 `localhost:9001` 登录 → 打开设计 → Connect MCP 插件（WS 走 `9001/mcp/ws`）。
- `status` / `doctor` 消除假阳性：明示"握手 Up ≠ 插件已连"，标注自托管入口 `9001/mcp/stream`、`4400/4401` 仅 npx 模式。

## 3. 变更清单

### 组 A — endpoint 事实源（基座）
1. `config.py::get_config` 增 `mcp_url`（读 `PENPOT_MCP_URL`）。
2. `mcp_spec.py::build_penpot_mcp_spec` url 改占位符，新增可选 `mcp_url` 参数（显式 URL 优先于占位符默认）。
3. `.env.example` 新增 `PENPOT_MCP_URL`（自托管 + SaaS 两示例）。

### 组 B — 模式重构（依赖 A）
1. `commands.py`：`cmd_remote` 重写为托管语义；npx 路径（原 remote-npx + mcp-only）打 deprecation warning。
2. `cmd_init` 向导选项与文案更新。
3. `client.py::register_claude_mcp` 支持带 query-token 的 URL（已天然支持，补测试）。

### 组 C — 自托管可用（依赖 A）
1. `commands.py`：新增 `print_self_hosted_onboarding`，`cmd_deploy` 调用。
2. `commands.py` / `doctor.py`：status/doctor 文案区分握手与插件连接，标注端口体系。

### 组 D — 文档与测试
1. `docs/reference/configuration.md`、penpot 命令 docstring、CHANGELOG fragment。
2. 测试矩阵见 §4。

## 4. 测试矩阵

1. `get_config` 读 `PENPOT_MCP_URL`（设/不设）。
2. `build_penpot_mcp_spec`：不设 → 占位符含默认本机 URL；显式传 → 用显式 URL。
3. `setup --with-penpot` 写的 spec 含 `${PENPOT_MCP_URL:-...}`。
4. deploy 注入 `.mcp.json` 的 `mcpServers.penpot.url` 为占位符字符串（不被 pydantic/渲染破坏）。
5. 新 `cmd_remote`：不起子进程；缺 `PENPOT_MCP_URL` 时报错并给引导。
6. `mcp-only` / npx 路径打 deprecation warning。
7. `cmd_deploy` 输出含自托管插件连接引导文案。
8. doctor/status 文案含端口体系说明。

## 5. 兼容性与迁移

- `remote` 语义反转属 breaking：旧依赖"SaaS+npx"行为者经 deprecation warning 引导迁移。
- 下游已部署的 `.mcp.json` 在下次 `cataforge deploy` 后由硬编码 URL 转为占位符；未设 `PENPOT_MCP_URL` 时行为等价（回退本机默认）。
- npx 链路保留，仅标记 deprecated，后续版本移除。
