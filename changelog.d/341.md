### Fixed

- **`deploy --rebuild` 不再静默抹掉 CLAUDE.md / AGENTS.md 的 §项目状态** —— `--rebuild` 的清场阶段过去会把 deploy-manifest 拥有的 instruction 文件一并删除，随后 section-merge 因失去"已存在文件"这个合并源而回退到 PROJECT-STATE.md 占位模板，静默覆盖 orchestrator 独占的章节。现按 `update_strategy == "section-merge"` 豁免这类有状态合并目标（`overwrite` 目标仍可清场），purge 后该文件保留、section-merge 正常保留用户/orchestrator 章节。
