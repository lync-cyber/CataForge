# C# · 代码评审细则

## 典型坏味道

- **`async void` 方法**：异常无法被调用方捕获，会直接崩溃进程；除事件处理器外一律改为 `async Task`
- **未 `await` 的 Task**：返回 `Task` 但调用处忘记 `await`，异常被静默吞掉；用 `_ = task` 显式丢弃或补 `await`
- **同步阻塞异步代码**：`.Result` / `.Wait()` 在 ASP.NET Core 中会导致死锁；必须全链路 async/await
- **`IDisposable` 未释放**：`SqlConnection` / `HttpClient`（直接 `new`）/ `Stream` 未用 `using`；评审时检查所有 `new` 资源型对象
- **`HttpClient` 错误使用**：每次请求 `new HttpClient()` 导致 socket 耗尽；应通过 `IHttpClientFactory` 注入

## 安全陷阱

- **SQL 注入**：字符串拼接构造 SQL，而非参数化查询（EF Core 参数化是默认行为，但 `FromSqlRaw` 直接插值仍有风险）
- **反序列化漏洞**：`Newtonsoft.Json` 的 `TypeNameHandling.Auto` 允许多态反序列化，可被利用；应显式禁用或迁移到 `System.Text.Json`
- **密钥 / 连接串硬编码**：不得出现在源码或 `appsettings.json` 提交中；应走 `Secret Manager` / 环境变量 / Key Vault
- **CORS 过度放开**：`AllowAnyOrigin() + AllowCredentials()` 在 ASP.NET Core 中会抛异常；生产环境须明确 `WithOrigins(...)`
- **路径遍历**：用户输入拼接文件路径须经 `Path.GetFullPath` + 前缀校验

## 常见缺陷模式

- **空引用**：Nullable Reference Types 已启用时编译器会警告，但 `!` 强制操作符滥用会绕开保护；评审时搜索 `!.` 使用是否合理
- **装箱**：`object` / `dynamic` 接收值类型、`string.Format` 传值类型、LINQ `Cast<object>` 均产生装箱；热路径中替换为泛型或 `Span<T>`
- **LINQ 多次枚举**：`IEnumerable<T>` 参数被多次 `foreach` 或多次调用 `Count()` 会多次执行查询；接收端用 `ToList()` / `ToArray()` 物化一次
- **捕获循环变量**：lambda 闭包捕获 `for` / `foreach` 变量时的延迟执行陷阱（C# 5+ `foreach` 已修复，但 `for` 中 `i` 仍需注意）

## 性能反模式

- `string` 拼接在循环中：用 `StringBuilder` 或 `string.Join` / 插值（编译器优化）
- `Task.Delay(0)` / `Thread.Sleep` 在生产代码中出现：通常是 busy-wait 或错误的同步原语，需追查意图
- `ToList()` 后再 `Where()`：先过滤再物化；避免将整表加载到内存再筛选
- 大对象频繁分配：超过 85 KB 的对象进入 LOH，GC 压力大；优先用 `ArrayPool<T>` / `MemoryPool<T>` 重用

## 评审 Checklist

1. 所有 `async` 方法是否返回 `Task` / `Task<T>` / `ValueTask`（而非 `void`）？
2. `CancellationToken` 是否传递到所有 I/O 调用？
3. `IDisposable` / `IAsyncDisposable` 资源是否被 `using` 保护？
4. 公共 API 参数是否有空值校验（`ArgumentNullException.ThrowIfNull`）？
5. 连接串 / 密钥是否从配置读取而非硬编码？
6. 数据库查询是否参数化（无字符串拼接 SQL）？
7. Nullable 注解是否与实际语义一致（无滥用 `!`）？
8. 日志是否用结构化 `ILogger`（无 `Console.WriteLine`）？
9. 异常信息未将 stacktrace / 内部细节直接返回给客户端响应？
10. 引用的 NuGet 包与 API 真实存在，无虚构的方法或参数？
