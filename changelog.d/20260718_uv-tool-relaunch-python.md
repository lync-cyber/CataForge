### Fixed

- **Windows uv tool 入口在中文系统上丢失隔离环境** —— UTF-8 重启现用
  `sys.executable` 替换 `sys.orig_argv[0]`，避免 uv trampoline 把重启进程导向不含
  CataForge 的基础 Python，修复 `cataforge --version` / `deploy` 启动即报
  `ModuleNotFoundError: No module named 'cataforge'`。
