### Fixed

- **Bootstrap setup 调用形式** —— ORCHESTRATOR-PROTOCOLS §Project Bootstrap Step 8、framework-update SKILL、PROJECT-STATE 模板与 CLAUDE.md §执行环境占位符统一指向 `python .cataforge/scripts/framework/setup.py --emit-env-block` / `--apply-permissions`；包 CLI `cataforge setup` 不提供这两个选项，原指引按包 CLI 形式调用会直接报错。
- **emit-env 迁移守护复活** —— 新增 `mc-0.9.2-setup-emit-env`（file_must_contain，守护 setup.py 的 `--emit-env-block` / `build_env_block`），接替因 `deprecate_after: 0.2.0` 永久 SKIP 的 `mc-0.1.5-setup-emit-env`；setup.py docstring 中的迁移检查引用同步指向新 id。
