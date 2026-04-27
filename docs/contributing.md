# 贡献指南

> 欢迎提交 Issue 与 PR。本文说明开发环境、代码规范、测试要求与文档维护约定。

## 开发环境

```bash
git clone https://github.com/lync-cyber/CataForge.git
cd CataForge
uv venv && uv pip install -e ".[dev]"
# source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate          # Windows
```

健康检查：

```bash
cataforge doctor
pytest -q
```

当前基线：`pytest -q` 应全量通过（具体数量见 `CHANGELOG.md`）。

> 依赖锁定：`uv.lock` 是仓库内的可复现性锁文件。修改 `pyproject.toml` 的依赖（包括 `[project.dependencies]` / `[project.optional-dependencies]`）后请运行 `uv lock` 刷新。CI 跑 `uv lock --check` 兜底，未刷新即 fail。

### 可选：装本地 pre-commit 钩子

`.pre-commit-config.yaml` 内置三个本地钩子（scaffold mirror 检查、ruff、workflow YAML 解析）。装一次即可：

```bash
pip install pre-commit
pre-commit install
```

CI 会跑同一组检查兜底，但本地装上能把"扫盘忘 sync mirror / 误改坏 workflow YAML"这类返工压到提交期发现。

---

## 代码规范

- **格式化**：`ruff format`
- **静态检查**：`ruff check`（规则集：`E, F, I, N, W, UP, B, SIM`）
- **类型检查**：`mypy --strict`
- **行宽**：100 列
- **目标 Python**：`py310`

提交前自测：

```bash
ruff format --check .
ruff check .
mypy src
pytest -q
```

---

## 测试

- 所有新功能附带测试，优先单元测试，集成测试覆盖关键路径
- 平台适配相关变更必须通过 `platform conformance tests`
- 回归测试基线：`pytest -q` 全量通过后再提 PR

```bash
pytest -q                            # 全量
pytest tests/platform/ -v            # 平台适配
pytest tests/deploy/ -v              # 部署编排
pytest --cov=cataforge --cov-report=term-missing
```

---

## 提交消息

遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

```text
feat(platform): add Cursor cross-platform mirror flag
fix(hook): prevent duplicate registration on re-deploy
docs(guide): restructure platforms.md
test(mcp): add lifecycle regression for stopped state
```

允许的 type（与 [`.github/workflows/pr-title.yml`](../.github/workflows/pr-title.yml) 校验列表对齐）：`feat` / `fix` / `docs` / `test` / `refactor` / `chore` / `perf` / `build` / `ci` / `release`。

---

## 分支与 PR

1. 从 `main` 切出功能分支（命名：`feat/<topic>` 或 `fix/<issue>-<topic>`）。
2. 保持 PR **原子性**，一个 PR 一个主题。
3. PR 描述包含：
   - 问题背景 / 解决方案
   - 测试方式
   - 相关 Issue 引用
4. CI 必须通过（`ruff` / `mypy` / `pytest`）。
5. 至少一位维护者 review 后合入。

---

## 文档维护约定

- 新增文档优先放入 `docs/` 下合适的子目录（`getting-started/` / `guide/` / `architecture/` / `reference/`）
- 根目录仅保留 `README.md` 与 `CHANGELOG.md`
- 新增 SVG 放 `docs/assets/`，必须遵循 [`assets/design-tokens.md`](./assets/design-tokens.md) 的色板、尺寸、字体与组件约定
- 所有文档内部链接使用**相对路径**，便于镜像与 fork（**例外**：根 `README.md` 在 PyPI 渲染时相对路径会 404，必须使用 `https://github.com/lync-cyber/CataForge/blob/main/...` 或 `https://raw.githubusercontent.com/...` 绝对 URL）
- 避免重复内容：同一主题应只存在于一处，其它位置通过链接引用

### 文档分层原则

四层结构（`getting-started/` → `guide/` → `architecture/` → `reference/`）与每层职责见 [`README.md`](./README.md) §文档分层原则。新写文档前先对号入座，避免写错层（例如把"原理"塞进 `guide/`）。

### 改代码 = 改文档

凡是触动以下"代码—文档"对应关系之一的 PR，必须在同一 PR 内同步对应文档；PR 模板的 "Doc impact" 区段强制确认。`scripts/checks/` 下的 anti-rot 守卫会在 CI 校验大部分对应关系。

| 代码改动 | 必须同步的文档 |
|----------|---------------|
| 新增 / 重命名 / 删除 Skill (`.cataforge/skills/<id>/`) | [`reference/agents-and-skills.md`](./reference/agents-and-skills.md) 总览表 + 折叠详细 + Skill 数 + Agent-Skill 矩阵；README/docs README 中的 "X 个 Skill" 计数（`scripts/checks/check_skill_count.py` 守护） |
| 新增 / 重命名 Agent | 同上，含 §Agent-Skill 关联矩阵 |
| 新增 CLI 子命令 (`cli/*_cmd.py`) | [`reference/cli.md`](./reference/cli.md) §命令总览 + 章节；[`reference/quick-reference.md`](./reference/quick-reference.md) 速查表 |
| 修改 `framework.json` schema 字段 | [`reference/configuration.md`](./reference/configuration.md) §framework.json 表（含 schema 示例 + preserve/overwrite 标注） |
| 增删 `platforms/<id>/` | [`guide/platforms.md`](./guide/platforms.md) + [`architecture/platform-adaptation.md`](./architecture/platform-adaptation.md) 能力矩阵 |
| 任何 BREAKING 行为变更 | `changelog.d/{PR#}.md` 加 `### Changed` 小节并在 bullet 显式标 BREAKING；`upgrade check` 会自动在升级前提醒用户 |
| 新增 / 弃用 `migration_check` | [`reference/configuration.md`](./reference/configuration.md) §migration_checks 表；新增需带 `release_version`，弃用补 `deprecate_after` |
| 任何用户可见变更 | `changelog.d/{PR#}.md` 片段（含 `### Added` / `### Changed` / `### Fixed` 等小节，`scripts/checks/check_changelog_fragments.py` 守护；纯文档/CI/重构 PR 可加 `[skip-changelog]` commit token 放行）。详见 [`changelog.d/README.md`](../changelog.d/README.md) |
| 发版（tag） | `scriv collect --version=X.Y.Z` 把 `changelog.d/*.md` 聚合到 `CHANGELOG.md` 顶部 `<!-- scriv-insert-here -->` 锚点；同时更新底部 `[X.Y.Z]:` reference link 表与 `[Unreleased]` 比较基线（`scripts/checks/check_changelog_link_table.py` 守护）。Windows 用 `PYTHONUTF8=1 scriv collect ...` |

---

## 新增平台适配

1. 在 `src/cataforge/platform/<id>.py` 实现 `PlatformAdapter`
2. 在 `.cataforge/platforms/<id>/profile.yaml` 声明能力与降级策略
3. 在 `pyproject.toml` 的 `[project.entry-points."cataforge.platforms"]` 注册
4. 添加 conformance 测试：`tests/platform/test_<id>_adapter.py`
5. 更新文档：
   - [`guide/platforms.md`](./guide/platforms.md)
   - [`architecture/platform-adaptation.md`](./architecture/platform-adaptation.md) 能力矩阵
   - [`guide/manual-verification.md`](./guide/manual-verification.md) 添加分节

---

## 新增 Skill / Agent

### Skill

1. 在 `.cataforge/skills/<id>/SKILL.md` 写定义（frontmatter + Markdown）
2. 脚本型 Skill 放同目录下的脚本（如 `main.py`）
3. 更新 [`reference/agents-and-skills.md`](./reference/agents-and-skills.md)
4. 添加测试：`tests/skill/test_<id>.py`

### Agent

1. 在 `.cataforge/agents/<id>/AGENT.md` 写定义
2. 如有专属协议文件，放同目录（如 `ORCHESTRATOR-PROTOCOLS.md`）
3. 更新 [`reference/agents-and-skills.md`](./reference/agents-and-skills.md) 清单与矩阵

---

## 发布流程（维护者）

发布由 GitHub Actions 通过 OIDC trusted publishing 自动完成（[`.github/workflows/publish.yml`](../.github/workflows/publish.yml)）；维护者只需在 main 上完成版本元数据并推 tag。

1. 在 feature 分支聚合 changelog 片段：`scriv collect --version=X.Y.Z` —— 读 `changelog.d/*.md` 全部片段，按 category 排序合并，在 `CHANGELOG.md` 的 `<!-- scriv-insert-here -->` 锚点上方插入 `## [X.Y.Z] — YYYY-MM-DD` 章节，删除已聚合的片段。再手动在 `CHANGELOG.md` 底部追加 `[X.Y.Z]:` reference link 与更新 `[Unreleased]: ...compare/vX.Y.Z...HEAD`（`scripts/checks/check_changelog_link_table.py` 守护）。
2. 升级 `src/cataforge/__init__.py` 中的 `__version__`（必须与 tag 数字位完全一致；publish.yml 在 tag push 时会校验三方一致：tag / `__version__` / CHANGELOG 章节均存在且唯一）。
3. 走正常 PR → squash merge 到 main。
4. 在 main 上打 tag 并推送：`git tag vX.Y.Z && git push origin vX.Y.Z`。
5. tag push 触发 `publish.yml`：自动 `python -m build` → `twine check dist/*` → 通过 OIDC（无需 API token）发布到 PyPI。前置条件：PyPI 已为本仓库配置 Trusted Publisher（`Owner: lync-cyber, Repo: CataForge, Workflow: publish.yml, Environment: pypi`，一次性配置完成）。
6. 在 GitHub 创建 Release，将本版 CHANGELOG 段作为 release notes。

---

## 行为准则

- 尊重他人
- 技术讨论对事不对人
- 假设善意

## 许可

贡献的代码将以项目的 [MIT 许可](../LICENSE) 发布。
