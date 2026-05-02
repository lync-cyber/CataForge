---
id: "arch-{project}-data"
version: "{ver}"
doc_type: arch
author: architect
status: draft
deps: ["prd-{project}"]
consumers: [tech-lead, developer, devops]
volume: data
volume_type: data
split_from: "arch-{project}"
required_sections:
  - "## 4. 数据模型"
---
# Architecture 分卷 — 数据模型: {项目名称}

[NAV]
- §4 数据模型 → §4.1 实体关系, E-001..E-{NNN}
[/NAV]

## 4. 数据模型

### 4.1 实体关系
```mermaid
erDiagram
    {实体关系定义}
```

### E-001: {实体名}
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|

### E-002: {实体名}
...
