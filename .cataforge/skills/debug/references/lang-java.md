# Java · 调试诊断细则

## 调试器

- **IDE 远程调试**：JVM 启动加 `-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005`；IDE 附加到端口 5005
- **jdb**：命令行调试器，适合无 GUI 环境；`jdb -attach 5005` 后用 `stop at`、`print`、`step` 等命令
- **条件断点**：在 IDE 断点上设置条件表达式（如 `userId == 42`），避免在高频路径全量中断

## 异常与 Stacktrace 解读

```
java.lang.NullPointerException: Cannot invoke "String.length()" because "str" is null
    at com.example.OrderService.process(OrderService.java:42)     ← 最近帧，优先看这里
    at com.example.OrderController.handle(OrderController.java:18)
    ...
Caused by: java.io.IOException: Connection refused
    at ...                                                          ← 根因链，从最深 Caused by 往上读
```

- 从最后一条 `Caused by` 找根因，再沿调用链往上找业务触发点
- Java 14+ 提供 **Helpful NullPointerExceptions**（默认开启），精确指出哪个变量为 null

## 常见运行时错误

| 错误 | 典型原因 | 定位思路 |
|------|---------|---------|
| `NullPointerException` | 未初始化字段、Optional 裸 get、返回 null | 读错误信息中的变量名；加 `Objects.requireNonNull` 哨兵 |
| `ClassCastException` | 泛型擦除、错误的类型断言 | 打印 `obj.getClass().getName()` 确认实际类型 |
| `StackOverflowError` | 无终止条件的递归、循环依赖初始化 | 看 stacktrace 中重复的帧确认递归路径 |
| `OutOfMemoryError: Java heap` | 内存泄漏、数据量估算不足 | 取堆转储分析；检查集合是否无界增长 |
| `OutOfMemoryError: Metaspace` | 动态类加载过多（如 Groovy/CGLIB） | 调大 `-XX:MaxMetaspaceSize` 并排查类生成逻辑 |
| `ConcurrentModificationException` | 迭代集合时修改 | 用 `CopyOnWriteArrayList` 或 `removeIf` 替代 |

先用线程 / 堆转储稳定复现再改，不凭最内层帧臆测；从最后一条 `Caused by` 读根因；每个修复配能复现原 bug 的回归测试。

## 日志与诊断

**日志**：
- 框架：SLF4J API + Logback 实现（Spring Boot 默认）
- 级别策略：`ERROR` 运营需介入；`WARN` 非预期但可恢复；`INFO` 关键流程节点；`DEBUG` 开发诊断（生产关闭）
- 参数化日志避免无谓字符串构建：`log.debug("user={}, order={}", userId, orderId)`；禁止字符串拼接传入

**JVM 诊断工具**：

| 工具 | 用途 | 命令示例 |
|------|------|---------|
| `jstack <pid>` | 线程转储，排查死锁/线程泄漏 | `jstack 1234 > thread.txt` |
| `jmap -dump` | 生成堆转储（.hprof） | `jmap -dump:format=b,file=heap.hprof <pid>` |
| `jcmd` | 多功能诊断（GC 统计、线程、堆） | `jcmd <pid> VM.native_memory` |
| **async-profiler** | 低开销 CPU/内存火焰图 | `./asprof -d 30 -f flamegraph.html <pid>` |
| **VisualVM / JMC** | GUI 实时监控、堆分析 | 连接本地或远程 JMX 端口 |

堆转储分析推荐 **Eclipse MAT**（Memory Analyzer Tool）：`File → Open Heap Dump` 后用 "Leak Suspects" 报告快速定位泄漏对象。
