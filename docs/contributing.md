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

1. 在 feature 分支更新 `CHANGELOG.md`（Keep a Changelog 格式）：补 `## [X.Y.Z] — YYYY-MM-DD` 段、`### Added/Changed/Fixed/BREAKING` 子段，并在底部 reference link 表追加 `[X.Y.Z]:` 与更新 `[Unreleased]: ...compare/vX.Y.Z...HEAD`。
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
