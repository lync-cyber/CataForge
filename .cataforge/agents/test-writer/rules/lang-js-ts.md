# JavaScript / TypeScript · 测试编写细则

## 主流测试框架选择

| 框架 | 推荐场景 |
|------|---------|
| Vitest | 新项目、Vite 栈、ESM 优先、TypeScript 原生支持 |
| Jest + @swc/jest | 存量 CJS 项目、React Native、大型遗留代码库 |

新项目默认选 Vitest：内置 TypeScript 支持、ESM 原生、与 Vite 配置共享，watch 模式下速度显著优于 Jest。

## 断言风格

使用 Vitest 内置的 `expect`（与 Jest API 兼容）：

```ts
import { describe, it, expect } from "vitest";

describe("add", () => {
  it("对两个正数求和", () => {
    expect(add(1, 2)).toBe(3);
  });

  it("抛出非数字参数错误", () => {
    expect(() => add("a" as any, 2)).toThrow(AppError);
  });
});
```

- 优先 `toBe`（基本值）/ `toEqual`（深比较对象）；避免过度使用 `toMatchSnapshot` 遮盖真实断言意图。
- 异步测试返回 Promise 或用 `async/await`，禁止裸 callback 形式。
- 断言须能真正失败，避免 `expect(x).toBeDefined()` 这类恒真断言；补齐边界与错误分支（`toThrow` / rejected promise），不要只测正常输入

## setup / teardown

```ts
import { beforeEach, afterEach, vi } from "vitest";

beforeEach(() => {
  // 重置共享状态
});

afterEach(() => {
  vi.restoreAllMocks(); // 自动恢复所有 spy/mock
});
```

全局 setup 文件在 `vitest.config.ts` 的 `setupFiles` 中注册，避免每个文件重复初始化。

## 参数化测试

```ts
import { test } from "vitest";

test.each([
  [1, 1, 2],
  [0, -1, -1],
  [100, 200, 300],
])("add(%i, %i) === %i", (a, b, expected) => {
  expect(add(a, b)).toBe(expected);
});
```

## Mock / Stub

```ts
import { vi } from "vitest";

// 模块级 mock
vi.mock("../services/email", () => ({
  sendEmail: vi.fn().mockResolvedValue({ ok: true }),
}));

// 函数 spy
const spy = vi.spyOn(logger, "error");
expect(spy).toHaveBeenCalledWith(expect.stringContaining("failed"));
```

- 只 mock 外部边界（网络、DB、时钟）；内部纯函数直接调用真实实现。
- 用 `vi.useFakeTimers()` 控制 `Date.now` / `setTimeout`，测试后调用 `vi.useRealTimers()`。

## 覆盖率

- 通过 Vitest 内置 `coverage: { provider: "v8" }` 生成覆盖率（无需额外安装 istanbul）。
- CI 设置覆盖率门禁（`thresholds.lines: 80`）；门禁数字在项目配置中统一维护，不在测试文件硬编码。
- 覆盖率仅作安全网，不以追求百分比为目的；集中覆盖业务核心路径与错误分支。
