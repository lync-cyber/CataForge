# JavaScript / TypeScript · 调试诊断细则

## 主流调试器

**Node.js 进程**

```bash
node --inspect-brk dist/index.js   # 在首行暂停，等待 debugger 连接
```

在 Chrome 打开 `chrome://inspect`，或在 VS Code 添加 launch 配置：

```json
{
  "type": "node",
  "request": "attach",
  "port": 9229,
  "skipFiles": ["<node_internals>/**"]
}
```

**前端 / 浏览器**：Chrome DevTools Sources 面板直接断点；React DevTools / Vue DevTools 用于组件状态检查。

**VS Code**：`launch.json` 的 `"runtimeExecutable": "tsx"` 可直接调试 TS 源文件而无需预编译。

## Stacktrace 与 Source Map 解读

- 生产构建开启 `sourcemap: "hidden"`（产物含 map 但不内联），将 `.map` 文件上传到 Sentry / Datadog 等错误追踪平台。
- 本地用 `source-map` 包手动解析：`node -e "require('source-map-support').install(); require('./dist/index.js')"` 可让 Node 自动还原行号。
- 遇到 `at Object.<anonymous> (bundle.min.js:1:12345)` 类混淆栈时，用 `npx source-map resolve <map> <line> <col>` 定位原始位置。

## 常见运行时错误

| 错误 | 排查方向 |
|------|---------|
| `TypeError: Cannot read properties of undefined` | 链式访问前未判空；用可选链 `?.` 后检查是否掩盖了上游 bug |
| `UnhandledPromiseRejection` | 找到未 `await` 或未接 `.catch()` 的 Promise；在 Node 中注册 `unhandledRejection` 事件打印完整栈 |
| `RangeError: Maximum call stack size exceeded` | 递归无终止条件，或循环引用触发序列化；用 `--stack-trace-limit=50` 增大栈帧输出 |
| `SyntaxError: Cannot use import statement` | ESM / CJS 混用；检查 `package.json` 的 `"type"` 字段与文件扩展名是否一致 |
| `EADDRINUSE` | 端口已占用；`lsof -i :<port>` 或 `netstat -ano` 找到占用进程 kill |

## 异步调试技巧

- `async_hooks` / Node.js AsyncLocalStorage 追踪跨异步边界的请求上下文（替代全局变量传 requestId）。
- `Promise.allSettled` 代替 `Promise.all` 防止单个 rejection 吞掉其他结果，调试时可看到全部状态。
- 在 `catch` 块加 `console.error(err.stack)` 而非只打 `err.message`，保留完整栈信息。
- 先稳定复现再动手：用 source map 还原压缩栈的真实位置，不凭栈臆测就改；每个修复配能复现原 bug 的回归测试，确认改前失败、改后通过

## 日志与 Profiling

- 结构化日志（`pino` / `winston`）输出 JSON，附 `requestId`、`level`、`timestamp`，便于日志聚合平台检索。
- Node.js CPU profiling：`node --prof` 生成 v8 log；`node --prof-process` 转换为可读报告；或用 `clinic.js` 一键火焰图。
- 内存泄漏：`node --expose-gc` + `process.memoryUsage()` 周期记录；Chrome DevTools Memory 面板拍多个堆快照对比增量对象。
