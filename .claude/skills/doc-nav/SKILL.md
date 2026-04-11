---
name: doc-nav
description: "文档导航与按需加载 — NAV-INDEX查询、精准章节加载。"
argument-hint: "<doc_id#section_id 如 arch#§2.M-001>"
suggested-tools: Bash, Read, Glob, Grep
depends: []
disable-model-invocation: false
user-invocable: true
---

# 文档导航与按需加载 (doc-nav)
## 能力边界
- 能做: 查询NAV-INDEX、按doc_id#section_id精准加载章节、提示前置依赖
- 不做: 文档内容生成(由doc-gen负责)、文档评审(由doc-review负责)
- 注: doc-nav 是 NAV-INDEX 的只读消费者，不修改 NAV-INDEX。

## 执行后端
`load_section.py` (位于 `.claude/scripts/load_section.py`) 是 load-section 指令的权威执行后端。Agent 应通过 Bash 调用它以获得真正的章节级提取（而非 Read 全文后人眼定位）。

**Bash 不可用时的降级路径**：若 Agent 未获 Bash 权限（如 architect/ui-designer/product-manager 等），按降级协议操作:
1. 通过 Read + offset/limit 打开目标文档
2. 先只读 [NAV] 块（通常在文件前 20 行）
3. 根据 [NAV] 标注的章节范围估算行号，再用 offset/limit 仅读取目标章节
4. 严禁一次性 Read 整篇超过 200 行的文档

## 操作指令

### 指令1: 加载文档章节 (load-section)
当Agent需要特定文档内容时:

**首选（Bash 可用）**：
```bash
python .claude/scripts/load_section.py <ref> [<ref> ...]
```
参数为一个或多个 `doc_id#§N[.item]` 引用，如 `prd#§2.F-001` 或 `arch#§3.API-001`。
- 脚本自动定位 `docs/{doc_type}/` 目录下匹配的文件（包含多卷场景）
- 仅输出目标章节内容（含嵌套子节），stdout 格式为 `=== <ref> ===\n<章节内容>\n`
- 退出码: 0=全部成功, 2=至少一个引用失败（错误写入 stderr）
- 批量调用优于循环单次调用，减少进程开销

**降级（Bash 不可用）**：
1. 读取 `docs/NAV-INDEX.md` 定位目标文档文件路径
2. 从文档的[NAV]块中，识别目标章节标题
3. 使用 Read 工具 + offset/limit 仅加载目标章节所在行区间
4. 如果章节有[DEPS]标注，提醒Agent注意前置依赖章节

### 指令2: 查看文档目录 (show-nav)
当Agent需要了解文档结构时:
1. 读取目标文档文件
2. 提取并返回[NAV]块内容

### 指令3: 查看全局索引 (show-index)
当Agent需要项目文档总览时:
1. 读取并返回 `docs/NAV-INDEX.md` 全文

## 路径格式
文档按类型存放在子目录中: `docs/{doc_type}/{filename}`

doc_type 目录映射见 doc-gen §template_id 映射表。reviews 子目录: doc/, code/, sprint/, retro/。

## NAV-INDEX格式
```
# NAV-INDEX: {project}
## 文档总览
| Doc ID | 文件路径 | 状态 | 分卷 | 章节数 |

## {doc_file}
[NAV]
- §1 章节名 → 子章节列表
[/NAV]
[XREF]
- F-001 → arch#M-001, ui-spec#P-001
[/XREF]
[DEPS: {依赖文档#章节}]
```

## 效率策略
- NAV-INDEX轻量，可常驻上下文
- 按章节加载 vs 全文加载 → 大幅减少上下文占用
- 每个章节独立可加载，不依赖文档其余部分
- 自动提示前置依赖，避免遗漏必要上下文
