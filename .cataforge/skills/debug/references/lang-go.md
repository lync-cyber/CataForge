# Go · 调试诊断细则

## 主流调试器

- **Delve**（`dlv`）是 Go 官方推荐的调试器，支持断点、变量检查、goroutine 列表。
  - 启动：`dlv debug ./cmd/app` 或 `dlv test ./pkg/foo`。
  - attach 到运行中进程：`dlv attach <pid>`。
- VS Code 配置 `launch.json` 选 `"type": "go"` 即调用 Delve 后端；GoLand 内置支持。
- 生产环境不使用交互式调试器；转用日志、pprof 和 trace。

## panic 与 stacktrace 解读

- Go panic 输出 goroutine 编号、状态和完整调用栈，格式：

  ```
  goroutine 1 [running]:
  main.foo(...)
      /app/main.go:12
  main.main()
      /app/main.go:7
  ```

- 关注 `goroutine 1 [running]` 下的首帧——通常是直接出错位置。
- `GOTRACEBACK=all` 环境变量让 panic 时打印所有 goroutine 栈，便于定位并发死锁。
- 在 HTTP handler 等框架层用 `recover()` 捕获 panic，记录完整 stacktrace 后返回 500。

## 常见运行时错误

- **nil 解引用**：`runtime error: invalid memory address or nil pointer dereference` — 检查返回 `*T` 的调用是否做了 nil 判断。
- **map 并发读写**：`concurrent map read and map write` — 必须用 `sync.RWMutex` 或 `sync.Map`。
- **数据竞争**：启用 race detector 定位：

  ```bash
  go test -race ./...
  go run -race main.go
  ```

  race detector 输出竞争的两个读写位置及对应 goroutine 栈；测试和 staging 环境常态开启。

- **slice/array 越界**：`runtime error: index out of range` — 检查循环边界和 slice 操作前的长度校验。
- 先用 `go test -race` / `GOTRACEBACK=all` 稳定复现再改，不凭栈臆测；不要用 `_` 吞掉 error 掩盖症状；每个修复配能复现原 bug 的回归测试

## 日志与结构化诊断

- 结构化日志使用 `log/slog`（Go 1.21+）：`slog.Info("request", "method", r.Method, "path", r.URL.Path)`。
- 日志级别：`DEBUG`（开发）、`INFO`（生产常态）、`WARN`/`ERROR`（需关注）；生产禁止全量 DEBUG。
- 在 context 中传递 request-id，日志和错误链均附带，便于跨服务追踪。

## 性能分析（pprof）

- 嵌入 HTTP pprof 端点：`import _ "net/http/pprof"`，访问 `/debug/pprof/`。
- CPU profile：`go tool pprof http://localhost:6060/debug/pprof/profile?seconds=30`。
- 内存 profile：`/debug/pprof/heap`；goroutine 泄漏：`/debug/pprof/goroutine`。
- 可视化：`go tool pprof -http=:8080 <profile_file>`（生成火焰图）。
- 执行追踪（调度延迟/GC 暂停）：`go test -trace trace.out ./... && go tool trace trace.out`。
