# Go · 实现编码细则

## 格式化与静态检查

- 所有代码提交前必须通过 `gofmt`（或 `goimports`）格式化；`goimports` 同时整理 import 块。
- 项目级静态检查使用 `golangci-lint`，启用以下 linter 作为基线：
  `errcheck`、`govet`、`staticcheck`、`gosimple`、`ineffassign`、`unused`。
- 配置文件 `.golangci.yml` 纳入版本控制；CI 与本地执行同一配置。

## 命名与可见性惯例

- 包名全小写、单词无下划线（`userservice` 而非 `user_service`）；导出名 PascalCase，未导出名 camelCase。
- 接口名以行为命名，单方法接口习惯加 `-er` 后缀（`Reader`、`Closer`）。
- 避免在包名已表达语义时重复（`log.Logger` 而非 `log.LogLogger`）。
- 常量组用 `iota` 枚举；`const` 块放在类型声明之后。

## 错误处理

- 错误必须处理，不得用 `_` 忽略（`errcheck` 守卫）。
- 向上包装错误使用 `fmt.Errorf("op: %w", err)`；用 `errors.Is` / `errors.As` 向下拆包。
- 哨兵错误（sentinel error）以 `var ErrXxx = errors.New(...)` 形式在包级声明，供调用方 `errors.Is` 匹配。
- `panic` 仅用于程序员错误（不变量被违反）；业务逻辑全部显式 `return err`。

## 项目结构

```
myapp/
  cmd/myapp/      # main 包，程序入口
  internal/       # 仅本模块可导入的私有实现
    domain/
    repository/
    service/
  pkg/            # 可被外部项目复用的公共包（慎放）
  go.mod
  go.sum
```

- 禁止在根包直接放业务逻辑；`main.go` 只负责配置注入和启动。
- `internal/` 下按**领域**而非**技术层**分包；避免 `util/`、`helper/` 等无意义包名。

## 常用标准库与惯用工具

- HTTP 客户端：`net/http`，复用 `http.Client`（禁止每次请求 `new(http.Client)`）。
- JSON：`encoding/json`；性能敏感场景评估 `github.com/bytedance/sonic` 或 `github.com/json-iterator/go`。
- 日志：`log/slog`（Go 1.21+）作为结构化日志默认选择。
- 配置：`os.Getenv` + 配置结构体；复杂场景用 `github.com/spf13/viper`。
- 共享状态的并发访问，编译器不查 data race，自测必跑 `go test -race`
- 调用标准库 / 第三方 API 前确认函数与签名真实存在，不要凭记忆拼名
