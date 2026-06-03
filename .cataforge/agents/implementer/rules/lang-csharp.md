# C# · 实现编码细则

## 格式化与 Lint

- 格式化工具：**dotnet format**（内置于 .NET SDK，无需额外安装）
- 静态分析：在 `Directory.Build.props` 启用内置 Roslyn 分析器：

```xml
<PropertyGroup>
  <Nullable>enable</Nullable>
  <ImplicitUsings>enable</ImplicitUsings>
  <AnalysisMode>Recommended</AnalysisMode>
  <TreatWarningsAsErrors>false</TreatWarningsAsErrors>
  <!-- CI 阶段可设为 true -->
</PropertyGroup>
```

- 风格规则写入仓库根的 `.editorconfig`；`root = true` 阻止父目录继承
- CI 中执行 `dotnet format --verify-no-changes` 验证格式一致性
- 可选引入 **StyleCop.Analyzers** 或 **SonarAnalyzer.CSharp** 追加更严格规则

## 命名与可见性惯例

| 元素 | 惯例 | 示例 |
|------|------|------|
| 类 / 接口 / 枚举 | PascalCase；接口加 `I` 前缀 | `OrderService`, `IRepository` |
| 公共方法 / 属性 | PascalCase | `GetOrderById`, `IsActive` |
| 私有字段 | `_camelCase` | `_orderRepository` |
| 局部变量 / 参数 | camelCase | `orderId`, `cancellationToken` |
| 常量 | PascalCase（非 ALL_CAPS） | `MaxRetryCount` |
| 异步方法 | 后缀 `Async` | `CreateOrderAsync` |

- 最小可见性原则：默认 `internal`；跨程序集公开时才用 `public`
- `sealed` 标注无继承意图的类，减少误扩展

## 错误处理惯用法

- 异常用于真正"异常"的情况（不可预见的外部错误、编程错误）；可预见的业务失败用 **Result 模式**（`OneOf` / `FluentResults` / 自定义 `Result<T,E>`）
- 所有取消点显式接受并传递 `CancellationToken`：`async Task DoWorkAsync(CancellationToken ct)`
- `using` 声明（C# 8+）管理 `IDisposable`：`using var conn = new SqlConnection(...);`
- 不要将异常用作控制流（try/catch 包住整个方法体做分支）
- 自定义异常继承 `Exception`，保留 `(string message, Exception inner)` 构造函数

## 项目与命名空间结构

```
MyApp.sln
├── src/
│   ├── MyApp.Domain/          # 领域实体、值对象、接口
│   ├── MyApp.Application/     # 用例、命令/查询处理器
│   ├── MyApp.Infrastructure/  # EF Core、外部 API 实现
│   └── MyApp.Api/             # ASP.NET Core Host
├── tests/
│   ├── MyApp.UnitTests/
│   └── MyApp.IntegrationTests/
└── Directory.Build.props
```

- 命名空间与文件夹路径保持一致；`<RootNamespace>` 写在各 csproj
- 共用构建属性集中到 `Directory.Build.props`；NuGet 版本集中到 `Directory.Packages.props`

## 常用 BCL 与惯用工具

| 需求 | 推荐 |
|------|------|
| JSON 序列化 | `System.Text.Json`（默认）；与第三方库集成时可选 Newtonsoft.Json |
| 集合查询 | LINQ（注意避免多次枚举 `IEnumerable`） |
| 路径操作 | `System.IO.Path` + `System.IO.File` |
| 配置读取 | `Microsoft.Extensions.Configuration`（`appsettings.json` + 环境变量） |
| 日志 | `Microsoft.Extensions.Logging.ILogger<T>`（注入，不静态引用） |
| 日期时间 | `DateTimeOffset`（带时区）存储；`TimeProvider` 用于可测试的时间依赖 |

调用 BCL / NuGet API 前确认方法与签名真实存在，不要凭记忆拼名；对可能为 null 的外部数据（JSON / DB 反序列化）显式处理，不要假设数据总是存在。
