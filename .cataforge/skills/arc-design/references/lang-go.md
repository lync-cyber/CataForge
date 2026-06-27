# Go · 架构师技术选型细则

## 依赖管理

- 使用 Go Modules（`go.mod` + `go.sum`）管理依赖，禁止 GOPATH 模式。
- 模块路径遵循域名前缀规范（如 `github.com/org/repo`）；内部私有模块配置 `GONOSUMCHECK` 和 `GONOSUMDB`。
- 优先选择依赖少、接口简洁的库；避免引入维护停滞或无 `go.mod` 的包。
- 选型前核实库的当前版本与维护状态，不沿用记忆中的旧默认；引用的第三方包须确认真实存在且 import path 正确，不要凭记忆拼写

## Web 框架选型

| 选项 | 适用场景 | 权衡 |
|------|---------|------|
| `net/http`（标准库） | 简单服务、微服务、库作者 | 零依赖、够用；路由需手写或配 mux |
| `chi` | 需要路径参数/中间件、兼容 `net/http` | 轻量，与标准库 100% 兼容 |
| `gin` | 性能敏感、团队熟悉、JSON API | 生态丰富；路由参数 API 与标准库不同 |
| `echo` | 类 gin、偏好 TLS/H2 配置简洁 | 接口设计略有差异，替换成本较低 |

**默认倾向**：小服务优先 `net/http` + `chi`；团队已有 gin 实践则沿用 gin。

## CLI 框架

- 默认选 `cobra`（支持子命令、flag 继承、shell 补全）。
- 极简单命令工具可直接用 `flag` 标准库，避免引入不必要依赖。

## 并发与运行模型

- **goroutine + channel** 是首选并发原语；channel 传递所有权，`sync.Mutex` 保护共享状态。
- 所有可取消操作必须接受并传递 `context.Context`（第一个参数）。
- 长驻 goroutine 必须有明确的退出路径（`select` 监听 `ctx.Done()`）；禁止裸启 goroutine 不处理退出。
- `sync.WaitGroup` 管理批量 goroutine；`errgroup`（`golang.org/x/sync/errgroup`）处理带错误聚合的并发。

## 类型系统与边界

- 以**接口**定义依赖边界，接口定义在消费方包，而非实现方。
- 泛型适用于容器、算法等通用结构；业务逻辑过度泛型化会降低可读性，审慎使用。
- 错误是值（`error` 接口）；自定义错误类型实现 `Error() string`，可选实现 `Unwrap() error`。

## 构建产物形态

- Go 默认编译为**静态单二进制**，无运行时依赖，适合容器部署。
- 交叉编译通过环境变量控制：`GOOS=linux GOARCH=amd64 go build`。
- 禁用 CGO 时设置 `CGO_ENABLED=0`，确保纯静态产物；需要 CGO 时记录原因并评估依赖风险。
