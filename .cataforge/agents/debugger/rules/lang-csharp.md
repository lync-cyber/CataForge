# C# · 调试诊断细则

## 主流调试器

| 工具 | 适用场景 |
|------|---------|
| **Visual Studio** | Windows 首选；内置诊断工具（CPU/内存/事件/线程） |
| **VS Code + C# Dev Kit** | 跨平台；支持断点、Watch、Call Stack、条件断点 |
| **JetBrains Rider** | 跨平台；内置内存分析、线程视图、EF Core 查询分析 |
| **dotnet-monitor** | 容器/生产环境；无需附加调试器即可触发 dump/trace/metrics |

- 容器内调试：镜像中保留 `vsdbg`（VS/VS Code remote attach）或使用 `dotnet-monitor` sidecar
- 远程附加：`dotnet-dbg attach <pid>` 或 VS"附加到进程"

## 异常与 stacktrace 解读

- **完整异常链**：`Exception.Message` 仅显示当前层，`Exception.ToString()` 包含 `InnerException` 和完整 stack trace；日志中始终记录 `ToString()` 或传入 `ILogger` 的 `exception` 参数
- **异步 stack trace**：.NET 8 异步方法产生"逻辑"堆栈（含 `async` 状态机帧）；`ExceptionDispatchInfo` 保留原始堆栈；搜索 `at async` 行定位实际抛出点
- **PDB 符号**：Release 构建默认生成 `.pdb`；部署时保留或上传到符号服务器（Azure Artifacts Symbol Server / SourceLink）以获得行号

## 常见运行时错误

**NullReferenceException**
- 根因：已启用 Nullable Reference Types 但用了 `!` 强制操作符掩盖警告，或外部数据（JSON / DB）反序列化为 `null`
- 诊断：检查 stacktrace 最内层帧的对象访问链，结合 Nullable 编译器警告；`??` / `?.` 应对可空路径

**死锁（Deadlock）**
- 根因：混用同步阻塞（`.Result` / `.Wait()`）与 `async/await`，或双向锁竞争
- 诊断：`dotnet-dump` 采集 dump → `analyze` → `syncblk` + `clrthreads` 查等待链；VS 的"线程"窗口查阻塞原因

**内存泄漏**
- 根因：静态事件订阅未取消、`IDisposable` 未释放、大对象缓存无边界
- 诊断：`dotnet-gcdump <pid>` → 用 VS / PerfView 分析对象图；`dotnet-counters monitor` 观察 GC Heap Size 趋势

**ObjectDisposedException**
- 根因：`using` 块外访问已释放对象，或 `IHostedService` 停止后异步任务仍在运行
- 诊断：检查生命周期管理，确认 `CancellationToken` 传递正确

先用 dump / 日志稳定复现再改，不凭单层 `Exception.Message` 臆测；记录完整 `Exception.ToString()`（含 InnerException），但不要将其返回给客户端；每个修复配能复现原 bug 的回归测试。

## 日志与诊断工具

- **结构化日志**：用 `ILogger<T>` 注入，配合 Serilog / NLog 输出 JSON；禁止 `Console.WriteLine` 在生产代码中出现

```csharp
_logger.LogInformation("Order {OrderId} created by {UserId}", order.Id, userId);
// 占位符为具名参数，非字符串插值（保留结构化字段）
```

- **dotnet-trace**：采集 CPU 采样 profile；`dotnet-trace collect --process-id <pid> --profile cpu-sampling`
- **dotnet-counters**：实时监控 GC、线程池、请求速率；`dotnet-counters monitor --process-id <pid>`
- **dotnet-dump**：采集 core dump；`dotnet-dump collect -p <pid>`，再用 `dotnet-dump analyze` 交互分析
- **EventSource / ActivitySource**：自定义追踪事件；结合 OpenTelemetry SDK 输出到 Jaeger / Zipkin / OTLP
