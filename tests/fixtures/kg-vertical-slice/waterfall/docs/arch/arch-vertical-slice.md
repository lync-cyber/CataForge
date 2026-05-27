---
doc_id: arch
doc_type: arch
---

# Architecture — vertical slice fixture (waterfall)

## §1 概览

后端单服务 + JWT；无数据库迁移，会话存内存。

### §1.4 TS-001 技术栈

- 后端: Python 3.12
- 认证: JWT (PyJWT)
- 会话: 内存存储

## §2 Modules

### §2.1 M-001 认证模块

- 映射功能: prd#§2.F-001
- 暴露 POST /login 接收 (email, password)，验证后签发 JWT。

### §2.2 M-002 会话模块

- 映射功能: prd#§2.F-002
- 暴露 POST /logout，使 server-side session 失效。
