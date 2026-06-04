### Fixed

- **`section-merge` 每次 deploy 删除 heading 后空行** —— `update_strategy: section-merge` 的 H2 解析正则 `\s*$`（`\s` 含换行）会连 heading 行尾换行一起吞掉,带走它与正文之间的空行;叠加 `_merge_fields` 丢弃空白 header、`_serialize` 不保证 section 之间有空行,使每次 `cataforge deploy` 都从 `CLAUDE.md` / `AGENTS.md` 删空行、产生 churn diff 并违反 MD022。正则收紧为 `[^\S\n]*$`、`_merge_fields` 保留 leading 空行、`_serialize` 在每个 `## ` heading 前强制空行,deploy 对规范 markdown 自此幂等。
