# Go · 代码评审细则

## 典型坏味道

- **忽略 error**：`result, _ = fn()` — 任何 error 必须处理或向上传播，用 `errcheck` linter 守卫。
- **裸 goroutine 泄漏**：启动 goroutine 未提供退出机制（`ctx.Done()` 或 channel 关闭），导致 goroutine 累积。
- **滥用 panic**：在业务逻辑中用 `panic` 替代错误返回；`panic` 仅限不变量违反的程序员错误。
- **过度接口抽象**：接口只有一个实现且无测试替身需求时，直接依赖具体类型即可。

## 安全陷阱

- **SQL/命令注入**：禁止拼接字符串构造查询，必须使用参数化查询（`database/sql` placeholder 或 ORM 绑定变量）。
- **数据竞争**：共享变量跨 goroutine 读写未加锁；评审时关注 `go test -race` 是否纳入 CI。
- **敏感信息泄漏**：日志、错误消息中不得包含密码、token、PII；`fmt.Errorf` 中避免透传外部输入。
- **路径穿越**：接受用户输入构造文件路径时必须用 `filepath.Clean` + 白名单前缀校验。

## 常见缺陷模式

- **nil map 写入**：`var m map[string]int; m["x"] = 1` → panic；必须 `make(map[string]int)` 初始化。
- **nil 指针解引用**：返回 `*T` 的函数调用结果未检查 nil 直接使用。
- **defer 陷阱**：`defer f(x)` 中 `x` 在 defer 注册时求值；需延迟求值时用 `defer func() { f(x) }()`。
- **循环变量捕获**（Go 1.21 前）：`for _, v := range slice { go func() { use(v) }() }` — goroutine 闭包共享同一 `v`；需在 Go 1.21 前显式 `v := v`。

## 性能反模式

- 在热路径中频繁小对象分配（建议 `sync.Pool` 或预分配 slice）。
- 字符串拼接循环内用 `+`（应用 `strings.Builder`）。
- 未复用 `http.Client`，每次请求创建新实例（默认不复用连接）。
- 传递大结构体时未使用指针（拷贝开销）；传递小结构体时过度使用指针（GC 压力）。

## 评审 Checklist

1. 所有 `error` 返回值均被处理或有意识地传播。
2. 每个 goroutine 有明确退出路径，不存在泄漏风险。
3. 接口定义位于消费方，实现层不反向依赖消费层。
4. 并发共享状态有锁保护或通过 channel 传递所有权。
5. 测试覆盖核心分支，关键路径有表驱动测试。
6. 敏感信息未出现在日志、error 消息或 HTTP 响应中。
7. `context.Context` 贯穿所有 I/O 调用，支持取消与超时。
8. 标准库与第三方 API 调用真实存在，无虚构的函数或签名
