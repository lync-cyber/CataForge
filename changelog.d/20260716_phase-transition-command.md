### Added

- **`cataforge phase transition` 复合命令** —— 把 Phase Transition Protocol 的确定性步骤链
  （doc-status 核验 / 依赖新鲜度 / reconcile / doc-consistency / 事件批量 / hygiene）代码化为
  一条幂等命令：全过 exit 0 并输出下一阶段 dispatch 提示；命中分支 exit 3 输出结构化选项，
  决策以 `--ack-stale-deps` / `--ack-inconsistency` / `--compact` 回传后重跑；事件批按日志
  最新 `phase_start` 去重，重跑不重复落盘，ack/compact 审计记录随批原子写入。

### Changed

- **Phase Transition Protocol 协议段收敛** —— ORCHESTRATOR-PROTOCOLS.md 该节由 10 步散文
  状态机（52 行）收敛为「状态持久化 + 门禁链命令 + 分支处置表 + 进入下一阶段」薄壳，
  步骤漏做/顺序漂移风险移交 CLI；相关锚点（Mode Routing / Revision / cascade_amendment /
  Bootstrap / META 事件表 / walkthrough 参照 / CLI 参考）同步改写。
- **`claude-md check` 判定收敛至 `limit_breaches`** —— 阈值比较逻辑上移
  `core/claude_md_hygiene.py`，CLI 检查与 phase transition hygiene 门共享同一判定权威。
- **doc-consistency 退出码文档修正** —— agents-and-skills.md 误记的「2 仅 MEDIUM/LOW」
  更正为引擎实际契约：0 通过（含 advisory）/ 1 存在 CRITICAL/HIGH，2 保留给坏参数。
