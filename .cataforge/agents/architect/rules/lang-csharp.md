# C# · 架构师技术选型细则

## 包与依赖管理

- **NuGet** 是唯一包源；使用 `<PackageReference>` 而非 `packages.config`
- 多项目解决方案启用 **Central Package Management**：在 `Directory.Packages.props` 统一声明版本号，子项目仅声明包名
- 固定可重现构建：启用 `packages.lock.json`（`<RestorePackagesWithLockFile>true</RestorePackagesWithLockFile>`）并提交到仓库
- 选型前核实包的当前版本与维护状态，不沿用记忆中的旧默认；引用的 NuGet 包与 API 须确认真实存在，不要凭记忆拼名

## 主流框架与分层选项

**Web API**

| 方案 | 适用场景 | 权衡 |
|------|---------|------|
| ASP.NET Core Minimal API | 新建服务、微服务、REPR 模式 | 简洁但需手动分层；路由声明分散于 `Program.cs` 时需 endpoint 分组 |
| ASP.NET Core MVC/Web API Controller | 大型团队、已有 MVC 代码库 | 结构固定，惯例多；相比 Minimal API 样板代码略多 |

**数据层**

| 方案 | 适用场景 | 权衡 |
|------|---------|------|
| EF Core（含 async 查询） | 需要迁移、关系型 CRUD、多数据库支持 | 抽象层高，复杂查询需 raw SQL 逃逸 |
| Dapper | 性能敏感、SQL 优先、存储过程封装 | 无迁移，需手写 SQL；映射需手动维护 |

**架构风格**：Clean Architecture（Domain / Application / Infrastructure / Presentation 四层）或 Vertical Slice（按功能切片）；中大型项目前者可追溯性更好，小型项目后者文件数更少。CQRS + MediatR 适合 Application 层命令/查询分离。

## 并发与运行模型

- **async/await + Task** 是 I/O 密集型服务的默认模型；`ConfigureAwait(false)` 用于库代码，ASP.NET Core 应用层无需设置
- **IAsyncEnumerable** 用于流式大数据集（分页、SSE、gRPC 流）；避免将整个结果集 `ToList()` 后再返回
- **Parallel.ForEachAsync / Channel\<T\>** 用于有界并发（批处理任务队列）；不要用 `Task.WhenAll` + 无限制并发度处理大批量
- 避免 `async void`（除事件处理器外）；避免 `.Result` / `.Wait()` 同步阻塞异步代码

## 类型系统与边界

- 项目级启用 **Nullable Reference Types**（`<Nullable>enable</Nullable>`）；所有公共 API 须消除编译器 nullable 警告
- **record** / **record struct** 用于不可变值对象（DTO、领域值类型）；`class` 用于有标识的领域实体
- 接口用于跨层解耦（依赖倒置）；避免为唯一实现创建接口（YAGNI）；泛型约束优先于运行时反射
- 统一用 `Microsoft.Extensions.DependencyInjection`（内置 DI）；仅在框架不满足时引入 Autofac / Lamar

## 构建产物形态

| 形态 | 命令 | 适用场景 |
|------|------|---------|
| Framework-dependent | `dotnet publish -c Release` | 容器部署，宿主已安装 .NET runtime |
| Self-contained | `dotnet publish -c Release --self-contained` | 无 runtime 宿主，部署简单 |
| Native AOT | `dotnet publish -c Release -p:PublishAot=true` | 启动极快、镜像极小；需全程 trimming 兼容 |

- 版本号单一事实来源：`Directory.Build.props` 的 `<Version>` 属性；遵循 SemVer
- NuGet 包发布额外需 `<PackageId>` / `<Authors>` / `<Description>`
