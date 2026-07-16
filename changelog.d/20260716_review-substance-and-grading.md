### Fixed

- **doc-review Layer 2 实质化** —— 收尾门禁不再「重形式、轻实质」：Layer 2 增加双层分工契约（形式面由 Layer 1 独占，AI 审查不复报可机检问题，严重度按缺陷对下游的影响定级）；prd / arch / ui-spec 按 doc_type 路由加载单份实质审查 profile（`review-prd.md` / `review-arch.md` / `review-ui-spec.md`），每份含实质维度（失败路径、NFR 兑现路径、状态覆盖等）、做 A 而非 B 对比锚点与严重度锚点；通用维度中的「规范性」归还 Layer 1。
- **code-review Layer 2 补正关注点与覆盖度** —— 新增「功能正确性(correctness)」维度并置顶（实现语义与 AC / 契约逐条对照，不以测试绿等价；算法/边界/数据完整性），`correctness` 进入 COMMON-RULES §统一问题分类体系与 `--focus` 合法值；review 模式补性能维度（挂载既有 lang-*.md 性能反模式细则）；维度按实质优先重排，convention 降末位且 Layer 1 lint 机检面不复报。
- **审查分级机制补密度与闭环** —— 聚类升级：同一 category × 同一 root_cause 的 MEDIUM 累计 ≥ `REVIEW_SYSTEMIC_MEDIUM_THRESHOLD`（5）时 reviewer 必须合并为一条系统性 HIGH（`members` 列成员，密度不裸计数）；revision 顺带修复：修订必修全部 CRITICAL/HIGH，同文件/同节内 MEDIUM/LOW 一并修复；notes 生命周期：re-review 时上轮未闭环 MEDIUM/LOW 逐条标 `still-open` / `resolved`，still-open 参与聚类升级计数。
- **测试套件性能纪律到达写测试上下文** —— 四条纪律（慢测标签分层 / 昂贵确定 setup 复用 / 进程内优先 / 并行就绪）移位为共享 reference `test-suite-performance.md`，tdd-engine 四档（RED dispatch / light-dispatch / light-inline / prototype-inline）prompt 全部注入；test-writer 自检清单增设第 5 条「套件性能」。

### Added

- **fast/full 两档测试口径** —— arch 模板新增 §7.4 测试执行口径（慢测标签约定 + `test_command_fast` 内循环 / `test_command_full` 收敛点门禁）；tdd-engine 内循环用 fast 档、三处收敛点验证用 full 档；arch 未声明 §7.4 时单命令双档同值向后兼容。
- **code-review scan 测试套件卫生探针** —— 内置 `test_hygiene` 检查（informational，scan 模式）：无标签慢测候选 / 每测重建昂贵 setup 候选，pattern 集走 plugin-style `rules/test-hygiene-{lang}.yaml`（6 语言，项目可整文件 override），文件级豁免 `cataforge: allow(test_hygiene, reason="...")`。
