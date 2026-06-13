# 迁移到 kg-first authoring

> 把一个 Markdown 先行（`context.strategy: doc-only`，或 `kg-first` 但 `authoring: md`）的存量项目切换到图权威 authoring（`authoring: graph`）。切换后文档由知识图谱导出，`docs/` 成为只读人审视图。

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

3. **切换 authoring 面** — 在 `.cataforge/framework.json` 设：

   ```json
   { "context": { "strategy": "kg-first", "authoring": "graph" } }
   ```

4. **验证** — 两道门禁应全绿：

   ```bash
   cataforge doctor            # context 配置门禁：strategy/authoring 一致
   cataforge context reconcile # 每文档 in_sync
   ```

切换后，Agent 经 context authoring（`write-doc` / `transact` / `write` / `write-narrative`）写图，`cataforge context finalize` 导出人审视图；人改导出文件由 reconcile 报 `human_edit`、`remediation: ingest`，经 `cataforge context ingest` 回流。

## 回退

authoring 面与权威方向纯由配置驱动，回退无需数据迁移：

- 暂留 md 先行：把 `context.authoring` 改回 `"md"`（图仍作镜像，reconcile 任一侧漂移都建议 `ingest` 回灌）。
- 完全退出图后端：把 `context.strategy` 改回 `"doc-only"`，图被旁路，`docs/` 重新成为唯一事实源。

> `context.authoring: "graph"` 必须与 `context.strategy: "kg-first"` 同时声明，否则 `cataforge doctor` 的 context 配置门禁 FAIL —— 图 authoring 没有 kg-first 后端就没有权威。
