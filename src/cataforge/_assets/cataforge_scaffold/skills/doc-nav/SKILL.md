---
name: doc-nav
description: "文档导航与按需加载 — 按 doc_id#§N 精准章节加载、依赖提示、token 预算控制。"
argument-hint: "<doc_id#section_id 如 arch#§2.M-001>"
suggested-tools: Bash, Read, Glob, Grep
depends: []
disable-model-invocation: false
user-invocable: true
---

# 文档导航与按需加载 (doc-nav)
## 能力边界
- 能做: 按 doc_id#§N[.item] 精准加载章节、批量加载、依赖链解析、token 预算分配
- 不做: 文档内容生成(由 doc-gen 负责)、文档评审(由 doc-review 负责)、索引重建(由 `cataforge docs index` 负责)

## 执行后端
权威后端是 `cataforge docs load` CLI 子命令（实现位于 `cataforge.docs.loader`）。Agent 应通过 Bash 调用以获得真正的章节级提取（而非 Read 全文后人眼定位）。

索引文件 `docs/.doc-index.json` 由 `cataforge docs index` 维护：含每个 doc_id / 章节 / item 的 `file_path` + `line_start` + `line_end` + `est_tokens` + `deps`。loader 命中索引走 O(1) 查表；索引缺失或过期时自动回退到 markdown 标题扫描。

**Bash 不可用时的降级路径**：若 Agent 未获 Bash 权限（如 architect/ui-designer/product-manager 等），按降级协议操作:
1. 读取 `docs/.doc-index.json` 获取目标文件路径和精确行号范围（line_start/line_end）
2. 使用 Read + offset/limit 精确读取目标章节
3. 若 `.doc-index.json` 不存在，运行 `cataforge docs index` 重建（或委派给可执行 Bash 的 agent）
4. 严禁一次性 Read 整篇超过 200 行的文档

## 操作指令

### 指令1: 加载文档章节 (load-section)
当 Agent 需要特定文档内容时:

**首选（Bash 可用）**：
```bash
cataforge docs load <ref> [<ref> ...]
```
参数为一个或多个 `doc_id#§N[.item]` 引用，如 `prd#§2.F-001` 或 `arch#§3.API-001`。
- 自动定位 `docs/{doc_type}/` 目录下匹配的文件（含多卷场景）
- 仅输出目标章节内容（含嵌套子节），stdout 格式为 `=== <ref> ===\n<章节内容>\n`
- 退出码: 0=全部成功, 2=至少一个引用失败（错误写入 stderr）
- 批量调用优于循环单次调用，减少进程开销

**可选标志**：
- `--json` — 输出结构化 JSON 数组 `[{ref, file_path, line_start, line_end, content, status}]`，避免章节内含 `===` 时分隔符冲突
- `--with-deps` — 自动解析并附带前置依赖章节（深度上限 2）
- `--budget N` — Token 预算：超出预算的 ref 转入 stderr 的 `[DEFERRED]` 列表，stdout 仅输出预算内章节

**降级（Bash 不可用）**：见上文"Bash 不可用时的降级路径"。

### 指令2: 查看文档索引 (show-index)
当 Agent 需要项目文档总览时:
1. 读取 `docs/.doc-index.json`，列出 `documents` 字段下的 doc_id → file_path → 章节列表
2. 若文件不存在，提示运行 `cataforge docs index`

### 指令3: 检查依赖 (show-deps)
当 Agent 需要了解某章节的前置依赖时:
```bash
cataforge docs load <ref> --with-deps
```
依赖关系来自 `.doc-index.json` 的 `deps` 字段（由 doc-gen 在生成时声明）。

### 指令4: 校验索引完整性 (validate)
当 Agent 怀疑索引漂移（doc 加载失败、ref 解析不到）时：
```bash
cataforge docs validate
```
只读校验：失败时 stderr 列出 orphan（缺 front matter 的 md）和 stale entry（索引指向已删文件）；exit 0=干净，3=需要 `cataforge docs index` 全量重建。

## 路径格式
文档按类型存放在子目录中: `docs/{doc_type}/{filename}`

doc_type 映射来自 `.cataforge/framework.json` 的 `docs.doc_types` 字段（缺省时使用内置默认 9 项: prd / arch / ui-spec / dev-plan / test-report / deploy-spec / research / changelog / brief）。下游项目可在 framework.json 自定义扩展。

## 效率策略
- 索引常驻 `.doc-index.json` 即可全局检索，无需常驻上下文
- 按章节加载 vs 全文加载 → 大幅减少上下文占用
- 同一 batch 内同文件多 ref 共享 per-file 缓存，减少重复 IO
- `--with-deps` 自动提示前置依赖，避免遗漏必要上下文
- `--budget` 在 token 紧张时把超额 ref 推迟，由 Agent 决定后续处理
