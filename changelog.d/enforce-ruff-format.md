### Changed

- **全仓 enforce ruff-format** —— pre-commit 与 CI 新增 `ruff format --check src tests scripts`，源码树一次性规范化为 canonical 格式。

此前 CI 只 enforce `ruff check`（lint）不 enforce format，而 `lint_format` PostToolUse hook 对 `.py` 编辑跑整文件 `ruff format`，导致编辑触碰的非 canonical 行被重排、在 diff 里产生无关 churn。现按与 lint 相同的范围（`src tests scripts`）enforce ruff-format，消除该漂移。

- **修正 `lint_format` hook 的 `.cataforge/` 跳过** —— 原先只对 `.md` 生效，现对所有文件类型生效，与 docstring 及 ruff 作用域（`src tests scripts`，不含 `.cataforge/`）一致；框架资产不再被自动格式化。
