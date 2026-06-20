# 测试 / E2E 真实性 API 参考

agent/skill 正文（每次调度加载的 prompt 上下文）保持语言无关，**不内嵌**具体测试框架 / e2e-driver 的 API 名。本文件按生态收纳这些 API，正文以 markdown 链接引用（见 CLAUDE.md §硬约束 2 与 [`check_no_language_coupling.py`](../../scripts/checks/check_no_language_coupling.py)）。新增生态在此追加一行。

## module-mock API（全量替换被测模块顶层导出的"虚假绿色"信号源）

| 生态 | module-mock API |
|------|----------------|
| JS/TS (Vitest) | `vi.mock(...)` |
| JS/TS (Jest) | `jest.mock(...)` |
| Python (stdlib) | `unittest.mock.patch` / `MagicMock` / `AsyncMock` |

**判定**：单元 / 集成测试至少有一条**不**用 module-mock 全量 stub 被测模块的顶层导出，否则接口契约无法被真实验证（sprint-review `ac-coverage` 维度复核）。

## e2e 真实用户输入原语（区别于 fixture / store 注入）

| 生态 | 键入 / 填充 / 点击原语 |
|------|----------------------|
| Playwright | `page.fill` / `page.click` / `page.type` / `keyboard.type` / `keyboard.press` |
| Cypress | `cy.type` / `cy.click` |
| Selenium | `element.send_keys` / `element.click` |

**判定**：e2e 套件至少含一处真实输入原语触发（非 `window.__*__` / `?e2e=1` 后门或 store / fixture 注入），作为 verdict=approved 前置条件。具体后门 + 真实输入正则按语言落在 `e2e-{lang}.yaml`（见 testing/SKILL.md §Plugin-style rules）。
