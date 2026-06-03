# Go · 测试编写细则

## testing 包基础

- 测试文件命名 `*_test.go`，与被测包同目录；外部黑盒测试用 `package foo_test`。
- 测试函数签名 `func TestXxx(t *testing.T)`；`t.Fatal` / `t.Error` 报告失败，前者立即终止当前测试。
- 断言推荐 `github.com/stretchr/testify/assert`（非致命）和 `require`（致命）；避免手写冗余 if 判断。

## 表驱动测试

表驱动是 Go 最主流的测试组织形式，适用于多输入/输出覆盖：

```go
func TestAdd(t *testing.T) {
    cases := []struct {
        name string
        a, b int
        want int
    }{
        {"正数相加", 1, 2, 3},
        {"含零", 0, 5, 5},
        {"负数", -1, -2, -3},
    }
    for _, tc := range cases {
        t.Run(tc.name, func(t *testing.T) {
            got := Add(tc.a, tc.b)
            require.Equal(t, tc.want, got)
        })
    }
}
```

## 子测试 t.Run

- 每个 case 用 `t.Run` 包裹，报错信息携带 case 名，便于定位。
- 子测试可并行：`t.Parallel()` 放在 `t.Run` 回调首行（注意捕获循环变量）。

## 测试 Setup 与 Teardown

- 全局初始化（如数据库连接）使用 `TestMain(m *testing.M)`：

```go
func TestMain(m *testing.M) {
    setup()
    code := m.Run()
    teardown()
    os.Exit(code)
}
```

- 单测级 cleanup 用 `t.Cleanup(func() { ... })`，无需手动 defer。

## Mock 与 Stub

- 依赖通过**接口**注入，测试时替换为 fake 实现或 mock。
- 自动生成 mock：`github.com/golang/mock/mockgen`（gomock）或 `github.com/vektra/mockery`。
- 简单场景手写 fake struct 即可，避免过度引入 mock 框架。

## 覆盖率

- 运行 `go test -cover ./...` 查看各包覆盖率。
- 生成 HTML 报告：`go test -coverprofile=coverage.out ./... && go tool cover -html=coverage.out`。
- 覆盖率目标因项目而异；核心业务逻辑以分支覆盖为导向，非追求百分比。
- 断言用 `require` / `assert` 且能真正失败，避免只断言 `err == nil` 的空壳；表驱动补边界、错误返回、nil 输入，不要只列正常 case
- 涉及 goroutine 的测试在 CI 跑 `-race`，捕获并发代码中的数据竞争
