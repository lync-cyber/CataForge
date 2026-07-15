---
id: prd
doc_type: prd
---

# PRD — vertical slice fixture (waterfall)

Minimal product requirements doc exercising the Alpha ingest codemod.
Maps directly to two arch Modules and two test-report TestCases.

## §1 概览

scope: 用户认证最小子集，含登录 / 登出两条业务流。

## §2 Features

### §2.1 F-001 用户登录

允许已注册用户用邮箱 + 密码完成身份认证。

#### AC-001 邮箱密码可登录

输入合法 (邮箱, 密码) 对返回 200 + JWT；失败返回 401。

### §2.2 F-002 用户登出

允许已登录用户终止当前会话，清空客户端 token。

#### AC-002 一键登出清空 token

调用 logout 接口返回 204；客户端本地 token 被擦除。
