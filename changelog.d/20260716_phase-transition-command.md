### Added

- **`cataforge phase transition` 复合命令** —— 把 Phase Transition Protocol 的确定性步骤链
  （phase-field 参数核验 / doc-status 核验 / 依赖新鲜度 / reconcile / doc-consistency /
  事件批量 / hygiene）代码化为一条幂等命令：全过 exit 0 并输出下一阶段 dispatch 提示；
  命中分支 exit 3 输出结构化选项，决策以 `--ack-stale-deps` / `--ack-inconsistency` /
  `--compact` 回传后重跑。决策与告警审计记录在挣得当轮即时落盘并按内容去重；4 条转换
  事件批的重跑判定为「日志最新 phase_start 即目标阶段且其后无源阶段流程类事件」，
  回退返工后的再次转换仍正常落盘，事件批写入失败以 FAIL 门报告而非裸异常。

### Changed

- **Phase Transition Protocol 协议段收敛** —— ORCHESTRATOR-PROTOCOLS.md 该节由 10 步散文
  状态机（52 行）收敛为「状态持久化 + 门禁链命令 + 分支处置表 + 进入下一阶段」薄壳，
  步骤漏做/顺序漂移风险移交 CLI；相关锚点（Mode Routing / Revision / cascade_amendment /
  Bootstrap / META 事件表 / walkthrough 参照 / CLI 参考）同步改写。
- **hygiene 门作用于平台指令文件** —— phase transition 的 hygiene 门经
  `resolve_instruction_file` 解析（AGENTS.md 平台不再恒 SKIP）；阈值判定上移
  `core/claude_md_hygiene.limit_breaches`，与 `claude-md check` 共享同一判定权威；
  `--compact` 实际改写即记审计事件，不再以复检 PASS 为前提。
- **阶段主文档识别容忍 `-lite` frontmatter** —— `docs/{doc_type}/` 子目录下声明
  `doc_type: {doc_type}-lite` 的文档不再被 phase status / transition 门误判为缺失。
- **check_prompt_cli_drift 扩展扫描组** —— 新增 `phase` / `event` / `claude-md` 组，
  prompt 资产引用这些命令的幻影动词开始被拦截。
- **doc-consistency 退出码文档修正** —— agents-and-skills.md 误记的「2 仅 MEDIUM/LOW」
  更正为引擎实际契约：0 通过（含 advisory）/ 1 存在 CRITICAL/HIGH，2 保留给坏参数。
