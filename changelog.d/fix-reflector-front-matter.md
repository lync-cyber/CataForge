### Changed

- **reflector RETRO / SKILL-IMPROVE 输出强制带 YAML front matter** —— §Output Contract 把 "无 front matter，indexer 自动跳过" 的例外说明撤掉，改为最小 frontmatter 强制（id / doc_type / status / date / author，SKILL-IMPROVE 额外 target_id / target_kind / source_exp）。下游 `cataforge docs validate` / `doctor` 不再把 retro 文件标为 orphan FAIL。§Retrospective Protocol 第 1 条注释更新为"存量旧版无 frontmatter 文件仍可入回顾分析，新产出按契约带 frontmatter"，与 §Anti-Patterns 新增的"禁止产出无 frontmatter"一致。闭环 issue [#105](https://github.com/lync-cyber/CataForge/issues/105)。
