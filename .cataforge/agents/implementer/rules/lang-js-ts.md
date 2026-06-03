# JavaScript / TypeScript · 实现编码细则

## 格式化与 Lint

- **Prettier**：代码格式化唯一事实来源，不与 ESLint 格式规则冲突（用 `eslint-config-prettier` 关闭重叠规则）。
- **ESLint flat config**（`eslint.config.js`）：继承 `tseslint.configs.recommendedTypeChecked`；开启 `@typescript-eslint/no-floating-promises`、`@typescript-eslint/no-explicit-any`。
- 提交前通过 `lint-staged` 只对暂存文件运行 Prettier + ESLint，避免全量扫描阻塞提交。

## 类型注解惯例

1. 函数公共接口（导出函数、类方法）须显式标注返回类型，不依赖推断。
2. 禁止 `any`；接受未知外部数据时用 `unknown`，再用类型守卫或 `zod.parse` 收窄。
3. 复杂对象优先用 `interface`（可 declaration merge）；联合 / 交叉类型用 `type`。
4. 枚举值用 `const enum` 或 `as const` 对象，避免运行时 JS 枚举对象的包体开销。
5. 泛型约束尽量具体（`T extends object` 而非裸 `T`），防止意外 `any` 传播。

## 错误处理惯用法

继承 `Error` 定义语义化错误类：

```ts
export class AppError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly cause?: unknown,
  ) {
    super(message, { cause });
    this.name = "AppError";
  }
}
```

- `async/await` 函数用 `try/catch` 包裹，禁止裸 `await` 不处理拒绝。
- 需要显式传播错误信息时用 Result 模式（`{ ok: true; data: T } | { ok: false; error: AppError }`），避免过度 throw。
- 顶层未捕获异常：Node 监听 `process.on("uncaughtException")` 与 `process.on("unhandledRejection")` 记录后退出。
- 调用第三方 SDK / 标准库 API 前确认方法与参数真实存在，不要凭记忆拼名

## 项目与模块结构

```
src/
  domain/       # 纯业务逻辑，无框架依赖
  infrastructure/ # DB、HTTP client、第三方 SDK
  application/  # 用例编排，串联 domain + infra
  api/          # 路由 / Controller，仅负责 I/O 转换
  shared/       # 跨层工具，禁止引用 domain 具体实现
```

- 每个模块目录含 `index.ts` 作为公共出口，内部实现文件不直接跨层引用。
- 路径别名（`@/domain`）在 `tsconfig.json` 的 `paths` 与打包工具中同步配置。

## 常用标准库与惯用工具

| 场景 | 推荐 |
|------|------|
| 运行时校验 | `zod` / `valibot` |
| 日期处理 | `date-fns` / `Temporal API`（现代环境） |
| HTTP 客户端 | `fetch`（原生）/ `ky`（轻量封装）|
| 环境变量解析 | `zod` + `dotenv` |
| 不可变数据 | `immer`（复杂状态树）|
