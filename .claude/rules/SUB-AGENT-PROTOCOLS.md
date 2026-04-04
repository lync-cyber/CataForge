# Sub-Agent Protocols

> 本文件仅包含子代理（非 orchestrator）在接收不同 task_type 时需要遵循的恢复/修订流程。
> 完整编排协议见 `.claude/agents/orchestrator/ORCHESTRATOR-PROTOCOLS.md`（仅 orchestrator 需要）。

---

## task_type=continuation 恢复流程

当子代理收到 task_type=continuation 时，执行以下恢复流程:
1. **加载中间产出** — 从 continuation 参数的 `上次中间产出` 文件路径列表中读取已完成的工作
2. **应用用户回答** — 将 `用户回答` 中的决策作为后续内容的依据，不再对已回答的问题重复提问
3. **定位恢复点** — 根据 `恢复指引` 确定应从 Skill Toolkit 的哪个步骤继续执行
4. **从恢复点继续** — 在已有中间产出基础上继续执行剩余步骤，使用 doc-gen write-section 就地编辑已有文档
5. **正常返回** — 完成后返回与 new_creation 相同格式的产出路径列表 + 执行摘要

注意: Continuation 是在中间产出基础上的恢复执行，文档已存在(status=draft)，直接编辑即可。

---

## task_type=revision 修订流程

当子代理收到 task_type=revision 时，执行以下修订流程:
1. **加载REVIEW报告** — 从 `docs/reviews/doc/` 找到编号最大的 `REVIEW-{doc_id}-r{N}.md`，或从 `docs/reviews/code/` 找到编号最大的 `CODE-REVIEW-{task_id}-r{N}.md` 加载审查报告
2. **分析问题列表** — 按严重等级排序 (CRITICAL > HIGH > MEDIUM > LOW)
3. **增量修复** — 仅修复 CRITICAL 和 HIGH 级别问题:
   - 使用 doc-gen write-section 修改相关章节
   - 不重新执行完整 Skill Toolkit 流程，除非 REVIEW 明确要求整章重写
4. **重新finalize** — 修复完成后调用 doc-gen finalize 更新文档
5. **返回产出路径** — 与新建任务相同的返回格式

注意: Revision 是在已有文档基础上的增量修订，不是从零开始。

---

## task_type=amendment 变更修订流程

当子代理收到 task_type=amendment 时，执行以下变更修订流程:
1. **加载变更分析** — 从 amendment 参数中读取 `<change-analysis>` XML 和用户变更描述
2. **定位影响章节** — 根据 affected_docs 中的 doc_id#section 引用定位需修订的章节
3. **增量修订** — 根据变更描述和 change_type 修订受影响的章节:
   - clarification: 仅澄清措辞，不改变语义
   - enhancement: 扩展已有定义，新增条目或修改约束
   - new_requirement: 新增章节或重大改写
4. **保持一致性** — 修订后检查内部交叉引用仍然有效
5. **重新finalize** — 修订完成后调用 doc-gen finalize 更新文档
6. **返回产出路径** — 与 new_creation 相同的返回格式

注意: Amendment 与 Revision 的区别 — Revision 以 REVIEW 报告为输入修复审查问题，Amendment 以变更分析为输入适应用户变更。
