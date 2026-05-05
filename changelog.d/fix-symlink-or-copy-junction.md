### Fixed

- **`cataforge bootstrap` / `deploy` 在 Windows + Python 3.11 / junction 已存在时炸成 `FileExistsError`** —— `symlink_or_copy` 的 cleanup 链漏掉了 Py3.11 上的 junction 形态：`Path.is_junction()` 是 3.12 才加的、`Path.is_symlink()` 对 junction 返回 `False`，落到 `shutil.rmtree(target)` 分支后又因为 `os.path.islink(junction)` 在 3.11 返回 `False` 可能递归进 source 树。提取 `_remove_target` helper：先 `os.path.lexists` 探测（含 dangling 链接），Windows + dir 形态时优先 `os.rmdir`（删 junction 不递归 source；对非空真目录 fail loudly 后回退 rmtree）；`copytree` fallback 前再 `lexists` 兜底，杜绝 `FileExistsError`。新增 9 个测试覆盖 dry-run / 缺父目录 / 真目录 / Unix 符号链接 / **Windows junction（v0.3.0 实际触发的 regression scenario）** / dangling 链接 / 空目标 / 重复部署幂等性。

### Changed

- **GitHub Actions 升到 Node.js 24 兼容版本** —— `actions/checkout@v4 → v5` / `actions/setup-python@v5 → v6` / `actions/upload-artifact@v4 → v5` / `actions/download-artifact@v4 → v5`，覆盖 `publish.yml` / `test.yml` / `anti-rot.yml` / `no-dogfood-leak.yml`。GitHub 计划 2026-06-02 把 Node 24 设为默认、2026-09-16 移除 Node 20 runtime，提前升级避免到期被 hard-fail。
