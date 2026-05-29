### Fixed

- **Windows 控制台脚本入口崩溃** —— `cataforge --version` / `--help` 经 console-script launcher（uv/pip trampoline，作为 zipapp 运行）启动时，`ensure_utf8()` 的 UTF-8 relaunch 逻辑把 `__main__.__spec__.name`（zipapp 下恒为字面量 `"__main__"`）当成 `-m` 目标重启，报 `ValueError: __main__.__spec__ is None`。重写为直接重放 `sys.orig_argv`（统一覆盖 console-script / `-m module` / `python script.py`，无需推断模块名），并把 relaunch 机制从 `os.exec*`（Windows 无真 exec，CRT 模拟在高输出量时 0xC0000005 崩溃）改为 spawn 子进程 + 转发退出码。新增 `tests/e2e/test_console_script_utf8.py`：以真实 console script + 剥离 `PYTHONUTF8`/`PYTEST_*` 的环境运行，是唯一能触发该 relaunch 分支的测试形态。
