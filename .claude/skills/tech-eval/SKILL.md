---
name: tech-eval
description: "技术评估 — 技术方案对比、选型决策、调研记录。"
argument-hint: "<评估领域如'前端框架'或'数据库选型'>"
suggested-tools: Read, Write, Edit
depends: [doc-gen, research]
disable-model-invocation: false
user-invocable: true
---

# 技术评估 (tech-eval)
## 能力边界
- 能做: 技术方案对比分析、选型推荐、产出调研记录
- 不做: 最终决策(由用户确认)、代码实现

## 输入规范
- 待评估的技术领域(如: 前端框架、数据库、API风格)
- PRD中的非功能需求约束

## 输出规范
- 方案对比表(优势/劣势/适用场景)
- 选型推荐(含理由)
- RESEARCH-NOTE记录(通过doc-gen产出)

## 执行流程
1. 明确评估维度(性能/生态/学习成本/维护性)
2. 调用research skill的web-search指令检索方案
3. 版本与生命周期验证 — 对每个候选方案:
   a. 通过web-search查询其最新稳定版本号和发布日期
   b. 确认维护状态(Active/LTS/Maintenance/EOL)
   c. 若候选方案已EOL或最新版本发布超过12个月未更新，标注风险并寻找替代
   d. 对比矩阵中使用验证后的最新稳定版，而非训练数据中的默认版本
4. 多方案对比 → 调用research skill的user-interview指令让用户比选
5. 记录选型决策和理由

## 效率策略
- 评估维度与PRD非功能需求对齐
- 选择题呈现选项，降低用户决策成本
