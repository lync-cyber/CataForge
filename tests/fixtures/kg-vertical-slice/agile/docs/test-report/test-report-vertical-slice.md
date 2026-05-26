---
doc_id: test-report
doc_type: test-report
---

# Test Report — vertical slice fixture (agile)

## §1 概览

冒烟测试套件 — 覆盖 prd §2 全部 AC。

## §2 用例矩阵

### §2.1 TC-001 登录冒烟

- 验证: prd#§2.AC-001
- 输入合法凭证，断言返回 200 + JWT。

### §2.2 TC-002 登出冒烟

- 验证: prd#§2.AC-002
- 登录后调用 logout，断言返回 204 + 客户端 token 已擦除。
