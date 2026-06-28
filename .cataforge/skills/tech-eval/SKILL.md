---
name: tech-eval
description: "技术评估 — 技术方案对比、选型决策、调研记录。当需要做技术选型、框架/库对比、数据库或 API 风格决策、技术栈权衡时使用。"
argument-hint: "<评估领域如'前端框架'或'数据库选型'>"
suggested-tools: file_read, file_write, file_edit
depends: [context, research]
disable-model-invocation: false
user-invocable: true
---

# 技术评估 (tech-eval)
## 能力边界
- 能做: 技术方案对比分析、选型推荐、产出选型决策记录（调研数据经 research 的 research-note 获取，本 skill 在其上附对比矩阵与推荐）
- 不做: 最终决策(由用户确认)、代码实现

## 输入规范
- 待评估的技术领域(如: 前端框架、数据库、API风格)
- PRD中的非功能需求约束

## 输出规范
- 方案对比表(优势/劣势/适用场景)
- 选型推荐(含理由)
- RESEARCH-NOTE记录(通过context产出)

## 执行流程
1. 明确评估维度(性能/生态/学习成本/维护性)
2. 调用research skill的web-search指令检索方案
3. 版本与生命周期验证 — 对每个候选方案:
   - 通过web-search查询其最新稳定版本号和发布日期
   - 确认维护状态(Active/LTS/Maintenance/EOL)
   - 若候选方案已EOL或最新版本发布超过12个月未更新，标注风险并寻找替代
   - 对比矩阵中使用验证后的最新稳定版，而非训练数据中的默认版本
4. 多方案对比 → 调用research skill的user-interview指令让用户比选
5. 记录选型决策和理由

## Anti-Patterns
- 禁止: 用训练数据中的默认版本号做"最新版"评估 —— 必须实际检索 release notes 验证；否则推荐过期版本
- 避免: 以训练集热门度做选型依据 —— 如不经评估直接推荐 "React + PostgreSQL + Redis" 组合；须用对比矩阵展示 ≥2 个备选并按 PRD 非功能需求打分，生态热度仅作其中一维、不得是唯一理由
- 禁止: 单一维度比较（"X 比 Y 快"）—— 性能 / 生态 / 学习成本 / EOL 风险 / license 至少四维并列才能产出可决策矩阵
- 禁止: 输出"看情况"等无承诺结论 —— tech-eval 的产出必须是带理由的明确推荐；含糊收尾让 architect 无法定稿 ARCH
- 避免: 把候选方案矩阵塞进 ARCH 主卷 —— 选型理由进 research-note 或 decision-log，ARCH 只承载终态决策
- 禁止: release notes / 版本检索不可达时退回训练数据默认值充当结论 —— 按 COMMON-RULES §通用 Error Handling 标 [ASSUMPTION] 注明未在线验证的版本假设与影响，不伪装成已验证推荐

## 效率策略
- 评估维度与PRD非功能需求对齐
- 选择题呈现选项，降低用户决策成本
