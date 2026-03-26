---
name: ui-design
description: "UI设计 — 页面布局、组件规范、交互流程、组件目录维护。"
argument-hint: "<prd文档路径或功能需求ID>"
suggested-tools: Read, Write, Edit
depends: [doc-gen, doc-nav, research]
disable-model-invocation: false
user-invocable: true
---

# UI设计 (ui-design)
## 能力边界
- 能做: 设计系统token定义、页面布局决策、组件规范定义、交互流程、响应式策略、组件目录维护(C-NNN注册/去重/合并)、设计token一致性检查
- 不做: 需求分析、架构设计、代码实现

## 输入规范
- prd#§2功能需求(F-{NNN})
- arch#§2模块划分(M-{NNN})

## 输出规范
- 设计系统token(色彩/排版/间距)
- 组件清单(C-{NNN})，含变体和Props
- 页面布局(P-{NNN})，含路由和状态流
- 导航与路由表
- 响应式断点策略

## 执行流程
1. 定义设计系统token
2. **[Penpot可选]** 若 CLAUDE.md `设计工具` 为 `penpot`，调用 penpot-sync 将token同步到Penpot项目和 tokens.css
3. 从PRD功能需求推导页面和组件需求
4. 设计风格不确定时 → 调用research skill的user-interview指令
5. 定义组件(变体/Props/交互)
6. 定义页面布局(路由/组件组合/状态流)
7. 规划响应式策略
8. 执行组件目录维护(见下方)
9. **[Penpot可选]** 若 CLAUDE.md `设计工具` 为 `penpot`，调用 penpot-review 验证设计文件与ui-spec的一致性

## 组件目录维护
在组件定义完成后，执行以下维护步骤:
1. 整理组件需求，去重合并同类组件
2. 为每个组件定义完整规范(变体/Props/交互)
3. 检查组件间一致性(token引用、命名风格)
4. 确保组件复用，避免重复定义
5. Token变量化，确保全局一致

## 效率策略
- 设计系统先行，确保组件一致性
- 组件复用优先，减少重复定义
