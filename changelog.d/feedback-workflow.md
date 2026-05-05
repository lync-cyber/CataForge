### Added

- **`cataforge feedback` CLI + `framework-feedback` builtin skill** —— 新增下游 → 上游反馈通道。三个子命令 `feedback bug` / `feedback suggest` / `feedback correction-export` 聚合 `cataforge doctor` + 最近 `EVENT-LOG` + `CORRECTIONS-LOG` 中的 `upstream-gap` 纠偏 + `framework-review` Layer 1 FAIL 摘要为 markdown body，通过 `--print` / `--out PATH` / `--clip`（pbcopy / wl-copy / xclip / clip）/ `--gh`（`gh issue create --body-file -`）四选一互斥 sink 发出。默认对 `<project>` / `~` 路径脱敏，`--include-paths` 显式关闭。配套 builtin skill `framework-feedback`（`record-to-event-log: true`，每次运行写一条 `state_change` 事件到 `EVENT-LOG`），方便 orchestrator / reflector 在累计 `upstream-gap` ≥ 阈值时自动调起。新增 `.github/ISSUE_TEMPLATE/feedback-from-cli.yml` issue 模板，字段与 CLI 输出 1:1 对齐；`bug_report.yml` 增加 tip 指引 `cataforge feedback bug --gh`。

### Changed

- **`correction record --deviation` 新增枚举值 `upstream-gap`** —— 与原 `framework-bug`（CataForge 框架缺陷）/ `self-caused`（下游自身偏离）正交，专表"上游 baseline 本身对此项目场景不对/不全"。`framework-feedback correction-export` 与 `cataforge feedback correction-export` 都按此 deviation 过滤聚合。`framework.json#features` 新增 `framework-feedback` 条目（`min_version: 0.3.0`，`auto_enable: true`，无 phase guard）。包版本由 0.2.1 → 0.3.0（minor bump：新公开 CLI 子命令组 + 新内置 skill + 新 deviation 枚举值，向后兼容）。
