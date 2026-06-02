### Added

- **`docs/.docignore`** —— 声明免于 doc-index orphan 检查的发布型文档子树，避免人工散文文档被误报为孤儿。

`find_orphan_docs` 原先只排除 `.archive/`，把所有缺 `id` front matter 的 `docs/**.md` 一律判为 orphan —— 对 SDLC 管线产物正确，对框架自身的 architecture/guide/reference 等人工文档是误报。新增 `docs/.docignore`（gitignore 风格：目录尾 `/` 或相对 docs/ 的 fnmatch 行，`#` 注释）声明非 SDLC artefact 子树；`cataforge docs validate` / `cataforge doctor` 读取它，匹配的无 front matter 文档不计为 orphan，改打印 `N doc(s) excluded by docs/.docignore` 以防静默放行。
