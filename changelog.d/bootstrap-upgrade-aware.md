### Changed

- **`/bootstrap` 命令改为升级感知统一入口** —— 先跑 `cataforge bootstrap` 幂等刷新/升级脚手架，再按项目指令文件存在与否分流从零初始化或环境补齐 + 恢复。

在已部署项目上重跑 `/bootstrap` 不再只做 from-scratch 初始化：它先委托 `cataforge bootstrap`（幂等 setup→upgrade→deploy→doctor）按磁盘状态决定是否刷新/升级脚手架，因此 `pip install -U cataforge` 后直接 `/bootstrap` 即可把脚手架带到最新；项目指令文件已存在时不重跑 Project Bootstrap，改走环境补齐 + `/start-orchestrator continue` 恢复。
