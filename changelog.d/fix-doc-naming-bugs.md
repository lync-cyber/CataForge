### Fixed

- **`cataforge docs load` 引用解析对带 `.` 的 doc_id 失败** —— `REF_RE` 的 `doc_id` 字符集是 `[\w-]+`，把 `prd-myapp-0.1.0#§1` 这类引用直接 reject 在 parse 阶段；现在 `cataforge docs validate` / `doctor` 会列出所有非 slug 形 id/alias 并 FAIL（exit 3），让根因在 index 阶段就暴露而不是在 load 时变成神秘的 parse error。

### Changed

- **doc-gen 命名规则：`id` 与文件名禁含版本号** —— `id` 改为稳定 slug `{template_id}-{project}`（仅 `[a-z0-9-]`），版本号下沉到新增的 frontmatter `version:` 字段。同步更新 SKILL.md、20 份 template、所有 agent 输出契约（PRD / ARCH / UI-SPEC / DEV-PLAN / TEST-REPORT / DEPLOY-SPEC / RETRO 等）。这样跨版本升级时 cross-ref 不会断链；旧的 `prd-myapp-0.1.0.md` 类文件名在 `docs validate` 下会被标为 invalid id。
