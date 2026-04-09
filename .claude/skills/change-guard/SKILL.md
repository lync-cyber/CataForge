---
name: change-guard
description: "变更守卫 — 分析用户变更请求与现有文档的一致性，决定处理路径。"
argument-hint: "<change_description: 用户变更描述>"
suggested-tools: Read, Glob, Grep
depends: [doc-nav]
disable-model-invocation: false
user-invocable: false
---

# 变更守卫 (change-guard)
## 能力边界
- 能做: 分析变更请求与已有文档的覆盖度、分类变更类型、评估影响范围、输出路由指令
- 不做: 修改文档或代码(仅分析和分类)、替代reviewer的审查职能

## 输入规范
- 用户变更描述 (自然语言)
- 当前项目已有文档 (通过doc-nav检索: PRD, ARCH, UI-SPEC, DEV-PLAN)

## 输出规范
- `<change-analysis>` 结构化分析结果，供orchestrator路由决策

## 操作指令: 分析变更请求 (analyze)

### Step 1: 变更描述解析
提取变更的核心意图:
- 涉及哪些功能领域 (用户故事/模块/接口/页面)
- 变更的性质 (新增/修改/删除)
- 预期影响范围

### Step 2: 文档覆盖度扫描
通过doc-nav检索已有文档，逐级检查:

1. **PRD**: 搜索相关功能 (F-NNN)、用户故事、验收标准 (AC-NNN)
2. **ARCH**: 搜索相关模块 (M-NNN)、接口 (API-NNN)、数据模型 (E-NNN)
3. **UI-SPEC** (如存在): 搜索相关组件 (C-NNN)、页面 (P-NNN)
4. **DEV-PLAN** (如存在): 搜索相关任务 (T-NNN)

记录每级文档的匹配结果:
- `covered`: 变更已被文档明确描述
- `partial`: 文档涉及相关领域但未完全覆盖该变更
- `missing`: 文档中无相关内容
- `conflicting`: 变更与文档现有描述矛盾

### Step 3: 变更分类
根据文档覆盖度结果分类:

| 覆盖度结果 | 变更类型 | 说明 |
|-----------|---------|------|
| 所有相关文档均 covered | `clarification` | 变更已有文档支撑，仅需澄清实现细节 |
| 至少一级文档 partial/missing，无 conflicting | `enhancement` | 变更扩展已有行为，需修订受影响的文档 |
| 存在 conflicting，或 PRD 级 missing | `new_requirement` | 变更引入新功能或与现有设计矛盾，需从PRD开始cascade |

### Step 4: 影响分析
对 `enhancement` 和 `new_requirement` 类型，进一步分析:

**Drift Level (偏移等级)**:
| Level | 条件 | 示例 |
|-------|------|------|
| L1 | 仅涉及文档表述优化，不改变行为 | 修改字段描述、补充注释 |
| L2 | 改变行为但不涉及架构，需更新AC | 增加API参数、修改验证规则、调整UI交互 |
| L3 | 涉及架构变更，需多级cascade | 新增模块、改变数据模型、修改系统边界 |

### drift_level 判定锚点
- **L1 (proceed)**: 仅修改文档措辞，不新增/删除/修改任何 F-xxx/M-xxx/API-xxx/E-xxx/T-xxx ID
- **L2 (amend_then_proceed)**: 修改现有 ID 的定义或新增 ID，但不涉及 arch#§1 架构概览中的系统边界
- **L3 (cascade_amendment)**: 涉及 arch#§1 系统边界变更、新增/删除顶层模块、或技术栈变更

**受影响文档** (affected_docs):
- 列出需要修订的文档 `doc_id#section` 引用
- 按上游到下游排序: PRD → ARCH → UI-SPEC → DEV-PLAN

**路由动作** (action): 见 ORCHESTRATOR-PROTOCOLS §Change Request Protocol。

### Step 5: 输出分析结果
返回结构化结果供orchestrator解析:

```xml
<change-analysis>
<type>clarification|enhancement|new_requirement</type>
<drift_level>L1|L2|L3</drift_level>
<coverage>
  <prd status="covered|partial|missing|conflicting">匹配的F-NNN/AC-NNN列表</prd>
  <arch status="covered|partial|missing|conflicting">匹配的M-NNN/API-NNN列表</arch>
  <ui_spec status="covered|partial|missing|conflicting|n/a">匹配的C-NNN/P-NNN列表</ui_spec>
  <dev_plan status="covered|partial|missing|conflicting|n/a">匹配的T-NNN列表</dev_plan>
</coverage>
<affected_docs>doc_id#section, ...</affected_docs>
<action>proceed|amend_then_proceed|cascade_amendment</action>
<rationale>分类理由的简要说明</rationale>
</change-analysis>
```

## 效率策略
- 通过doc-nav按需加载，不全量读取所有文档
- 优先检查PRD级覆盖度（决定是否为new_requirement），再检查下游
- 对clarification类型快速返回，不做深度影响分析
