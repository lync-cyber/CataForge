# 迁移到 graph 模式（图权威 authoring）

> 把一个 Markdown 先行（`context.mode: markdown`，或升级前仍带已退役 `strategy`/`authoring` 双轴）的存量项目切换到图权威（`context.mode: graph`）。切换后文档由知识图谱导出，`docs/` 成为只读人审视图。

## 前提

- 项目已有 `docs/<doc_type>/*.md` 业务文档，且带合规 YAML front matter（`cataforge context validate` 通过）。
- `.cataforge/kg/store` 已初始化（`cataforge kg init`）。

## 迁移步骤

1. **种子灌入** — 把现有 Markdown 抽取进图：

   ```bash
   cataforge context ingest
   ```

2. **建立导出基线** — 从图导出 `docs/` 并写入每文档的导出哈希基线：

   ```bash
   cataforge context finalize
   ```

   此后 `cataforge context reconcile` 对每个文档报 `in_sync`（`remediation: none`）。

3. **切换 mode** — 在 `.cataforge/framework.json` 设：

   ```json
   { "context": { "mode": "graph" } }
   ```

   若仍残留退役键 `context.strategy` / `context.authoring`，删除它们（`cataforge doctor` 会对残留键 FAIL；运行时 `context_mode()` 只读 `context.mode`）。

4. **验证** — 两道门禁应全绿：

   ```bash
   cataforge doctor            # context 配置门禁：mode 合法、无退役键
   cataforge context reconcile # 每文档 in_sync
   ```

切换后，Agent 经 context authoring（`write-doc` / `transact` / `write` / `write-narrative`）写图，`cataforge context finalize` 导出人审视图；人改导出文件由 reconcile 报 `human_edit`、`remediation: ingest`，经 `cataforge context ingest` 回流。

## 回退

mode 纯由配置驱动，回退无需数据迁移：

- 完全退出图后端：把 `context.mode` 改回 `"markdown"`，图被旁路，`docs/` 重新成为唯一事实源。

> 合法取值仅 `graph` / `markdown`。勿再写入已退役的 `context.strategy` / `context.authoring`。
