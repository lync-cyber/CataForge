### Changed

- **`/self-update` skill 与 `/bootstrap` command 合并为 `framework-update` skill** —— 单一 `/framework-update [check|apply|verify]` 覆盖整条框架生命周期。

两个旧入口都是 `cataforge bootstrap` 脊柱的薄包装，对同一调用协议各写一遍。合并后脊柱只描述一处：`apply` 串起条件包升级（pip/uv）→ `cataforge bootstrap` 幂等刷新/部署/验证 → upgrade.state 与框架版本簿记 → 按项目指令文件存在与否分流项目初始化或恢复。在已部署项目上重跑 `apply` 等价于一次升级检查 + 刷新，再分流 from-scratch 初始化或环境补齐 + `/start-orchestrator continue` 恢复。`/bootstrap` command 作为纯重复包装移除；`framework-update` 既 user-invocable 又 model-invocable，直接 `/framework-update` 调用。CLI `cataforge bootstrap` / `cataforge upgrade` 不变。
