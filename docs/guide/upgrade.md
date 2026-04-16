# 升级与脚手架刷新

> CataForge 采用 **包管理器驱动** 的升级模型：包本身走 `pip` / `uv tool`，项目内 `.cataforge/` 脚手架由 `cataforge upgrade apply` 刷新。**不存在** "远程自升级"。

## 升级四步法

```bash
# 1. 对比 "已安装包版本" vs "项目 scaffold 版本"
cataforge upgrade check

# 2. 升级包本身
pip install --upgrade cataforge          # 或: uv tool upgrade cataforge

# 3. 刷新项目 scaffold（保留用户可编辑字段）
cataforge upgrade apply
#   --dry-run 可预览会刷新哪些文件

# 4. 验证：现在应打印 "Scaffold is up to date with the installed package."
cataforge upgrade check
```

`cataforge upgrade verify` 是 `cataforge doctor` 的别名，检查迁移项是否全部通过。

---

## 字段保留规则

`upgrade apply`（等价于 `setup --force-scaffold`）刷新时会保留用户字段：

| 文件 | 保留项 | 覆盖项 |
|------|-------|-------|
| `framework.json` | `runtime.platform`、`upgrade.state` | `constants` / `features` / `migration_checks` / `upgrade.source` / `version` |
| `PROJECT-STATE.md` | 整个文件 | — |

> `framework.json` 的 `version` 字段在每次 scaffold 写入时由当前安装包的 `cataforge.__version__` **实时戳入**，确保 `upgrade apply` 后 `upgrade check` 立刻报告 "up to date"。

---

## 迁移检查（Migration Checks）

`cataforge doctor` 会执行 `migration_checks` 段落声明的全部检查项。任一 FAIL 时进程返回码为 1，可用作 CI gate：

```bash
cataforge doctor || exit 1
```

常见检查项：

- `framework.json` / `hooks.yaml` 结构完整性
- 4 个平台 `profile.yaml` 合法性
- 关键文件存在与权限
- 依赖 IDE 产物的检查（未 deploy 前显示 `SKIP`，不会 FAIL）

---

## 常见升级场景

### 场景 1：只升级包，不刷新 scaffold

```bash
pip install --upgrade cataforge
cataforge upgrade check     # 会报告 scaffold outdated
# 不执行 upgrade apply → 保持旧 scaffold 行为
```

适合 "新版本 CLI 对旧 scaffold 仍兼容" 的保守场景。

### 场景 2：纯预览，不改动任何文件

```bash
cataforge upgrade apply --dry-run
```

输出 "will refresh ..." 清单，不写盘。

### 场景 3：回滚

包回滚：`pip install cataforge==0.1.1`。
Scaffold 回滚：需走 git（`git checkout -- .cataforge/`）。

---

## 参考

- CLI 命令参考：[`../reference/cli.md`](../reference/cli.md)
- 配置文件清单：[`../reference/configuration.md`](../reference/configuration.md)
- `doctor` 用作 CI gate：[`manual-verification.md`](./manual-verification.md)
