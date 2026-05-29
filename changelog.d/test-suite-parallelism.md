### Changed

- **测试套件并行化与 fast/slow 归类修正** —— `tests/e2e/test_docs_nav.py` 补 `pytest.mark.slow`，不再在 fast unit 矩阵触发 wheel+venv 构建；fast CI 步骤改用 `pytest -n auto --dist loadscope`（新增 `pytest-xdist` dev 依赖）。Linux leg 的 uv 冒烟由全量重跑收敛为 `tests/cli`+`tests/core` 子集，KG 注入回归命名门禁限 Linux。本地 fast 套件墙钟由约 375s 降至约 60s。

### Fixed

- **`kg/test_codegen.py` codegen 重复执行** —— 只读断言共享 session 级 codegen 产物，linkml 生成由 5 次降为 2 次。
- **`mcp` 生命周期测试 teardown 超时** —— `test_start_cleans_stale_running_state` 的 `_pid_alive` patch 对真实 pid 委托真实实现，避免 stop() 空耗 SIGTERM+SIGKILL 超时（单测由约 10s 降至约 0.1s）。
