# Changelog Fragments

每个 PR 在此目录加 1 个 markdown 片段，记录该 PR 的用户可见变更。发版时 `scriv collect` 会把所有片段聚合到 `CHANGELOG.md` 并删除片段。

## 文件命名

```
{PR编号}.md
```

例：`84.md`、`85.md`。一个 PR 1 个文件即可——多 category 用文件内的小节区分（见下）。

## 文件内容格式

每个片段是一段 markdown，按 Keep-a-Changelog 的 6 个 category 用 `### {Category}` 小节分组（**只用本 PR 实际涉及的 category**）：

```markdown
### Added

- **新特性 A** —— 一句话说明 + 关键路径 / 参数 / 行为差异。

### Changed

- **修改的现有行为** —— 同上。

### Fixed

- **修复的 bug** —— 同上。
```

可用 category：`Added` / `Changed` / `Fixed` / `Removed` / `Deprecated` / `Security`。

可参考 `CHANGELOG.md` 既有 `[0.1.x]` 段的写法（精炼"为什么 + 怎么做"，避免照抄 commit message）。

## 创建片段（推荐用 scriv）

```bash
scriv create --add  # 创建并自动 git add
```

scriv 默认会用随机 ID 命名（如 `20260427_142531_my-branch.md`）；CataForge 的约定是改名为 `{PR#}.md`，提交前手动 rename 一次即可。

或直接手动新建（无需装 scriv）：

```bash
$EDITOR changelog.d/85.md  # 编辑后 git add
```

把 `.template.md.j2` 的内容复制过去当起手即可。

## 跳过片段（罕见）

下列场景不需要加片段（CI 守卫会按 commit-message token 放行）：

- 纯文档修订（README / docs/）
- CI / 构建脚本 only 改动
- 测试 only 改动
- 重构无用户可见行为变化

在任意一条 commit message 加 `[skip-changelog]` token 即可放行：

```bash
git commit -m "refactor(loader): extract _resolve_path helper [skip-changelog]"
```

## 发版聚合

维护者在打 tag 前：

```bash
# Linux / macOS
scriv collect --version=0.2.0

# Windows（scriv 默认按 cp1252 读 markdown，需切 UTF-8 模式）
PYTHONUTF8=1 scriv collect --version=0.2.0
```

scriv 会：
1. 读 `changelog.d/*.md` 全部片段（跳过 `README.md` / `.template.md.j2`）
2. 按 category 排序合并
3. 在 `CHANGELOG.md` 的 `<!-- scriv-insert-here -->` 锚点上方插入新版本块
4. 删除已聚合的片段

聚合后还需手动：
- 在 `CHANGELOG.md` 底部追加 `[X.Y.Z]: https://github.com/.../releases/tag/vX.Y.Z` reference link
- 把 `[Unreleased]: ...compare/vY...HEAD` 比较基线改为新 tag

`scripts/checks/check_changelog_link_table.py` 会守护这两条。


## 已知陷阱

- **不要在 bullet 里直接写 `<!-- ... -->` HTML 注释**（即使包在反引号里）—— scriv 会把整段 fragment 静默丢弃。需要描述该锚点时用 `scriv-insert-here 锚点` 字面文字描述即可。

## 历史

- 2026-04-27 引入（PR #85），替代直接编辑 `CHANGELOG.md` 的工作流
- v0.1.x 及更早条目原样保留在 `CHANGELOG.md`，未回填为片段
