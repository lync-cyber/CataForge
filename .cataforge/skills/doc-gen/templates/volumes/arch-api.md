---
id: "arch-{project}-{ver}-api"
doc_type: arch
author: architect
status: draft
deps: ["prd-{project}-{ver}"]
consumers: [tech-lead, developer, devops]
volume: api
volume_type: api
split_from: "arch-{project}-{ver}"
required_sections:
  - "## 3. 接口契约"
---
# Architecture 分卷 — 接口契约: {项目名称}

[NAV]
- §3 接口契约 → API-001..API-{NNN}
[/NAV]

## 3. 接口契约

### API-001: {接口名称}
```yaml
path: /api/v1/{resource}
method: POST
module: M-001
request:
  headers: { Authorization: "Bearer {token}" }
  body:
    field1: { type: string, required: true, desc: "{}" }
response:
  200: { schema: "{ResponseType}" }
  400: { schema: "ErrorResponse" }
```

### API-002: {接口名称}
...
