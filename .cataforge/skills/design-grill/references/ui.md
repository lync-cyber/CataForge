# UI Grill profile

## 目标与上游边界

在 PRD 和 Arch 已确定的语义、功能和技术边界内，澄清任务、信息层级、交互状态、视觉系统、响应式和可访问性决定。

- 改变功能、业务流程、权限或交互语义的分支交回 PRD
- 改变 API、数据、系统能力或实现边界的分支交回 Arch
- 不用视觉设计掩盖上游缺口

## 事实来源

按通用本地事实优先规则，重点读取：

- PRD 功能、用户场景、交付面与 AC
- Arch 模块、API、权限、数据能力与技术约束
- 现有 UI-SPEC、设计系统、`tokens.css`、组件代码和渲染结果
- 用户提供的品牌规范、视觉参考与 `design_tool` 配置
- Penpot 可用时，经 Capability Gate 后用 penpot-bridge `read` 读取组件结构、样式与 Token 实值；必要时 `export_shape` 做视觉 grounding

## 决策树

1. 用户主要任务、使用环境和注意力条件
2. 信息架构、任务优先级和内容密度
3. 产品调性、品牌约束和视觉参考
4. 核心用户流和导航模型
5. loading/empty/populated/error、权限不足、离线等状态
6. 可访问性、本地化和内容伸缩约束
7. 响应式断点及小屏行为
8. `design_tool=penpot` 时确认 doc-first 或 Penpot-first 的视觉实值权威
9. 色彩、排版、间距、圆角和动效原则
10. 页面、组件、状态变体和复用边界

不得在上游节点未决时先问色值、圆角或单组件外观。

## 推荐依据

- 用户任务效率、信息层级与认知负担
- 已有品牌、设计系统、资产和渲染证据
- WCAG、可访问性、本地化和内容伸缩约束
- PRD/Arch 的实际能力、跨页面一致性和组件复用

## 自动建议条件

仅在以下高影响情形一次性建议 Grill：任务优先级或信息层级影响多页；调性与品牌资产冲突；存在根本不同的导航或交互模型；关键状态未定义；可访问性、本地化或移动端是关键约束；UI-SPEC、代码、Token 或 Penpot 互相矛盾；即将 author Token 但 doc-first/Penpot-first 未定。普通颜色偏好或单组件样式缺口不足以建议。

## Penpot 与产物归属

- 语义契约始终归 UI-SPEC；视觉实值按既有 doc-first/Penpot-first 规则保持唯一权威源
- Grill 不切换 authoring surface；Penpot 不可用时遵循 Capability Gate，不声称已读取
- Grill 只调用 penpot-bridge `read` 核验事实；Token 同步留给 ui-design 正式流程，不得调用 `generate` 或 `verify`
- Penpot 不得覆盖组件身份、Props、状态枚举或 PRD 映射
- 调性和策略映射 UI-SPEC §0；Token 决定映射 §1；组件与状态映射 §2；页面与状态流映射 §3；导航映射 §4；响应式映射 §5
- 调研、参考比较和被否决方案保留在该阶段单份 research-note；UI 决定不创建 ADR，实质架构决定交回 Arch
