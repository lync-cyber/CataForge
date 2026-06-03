# Rust · 代码评审细则

## 典型坏味道

- **`unwrap()` / `expect()` 滥用**：生产路径出现 `unwrap()`/`expect()` 须确认确实是不可能失败的不变量，否则要求改用 `?` 或显式错误处理。测试代码中 `unwrap()` 可接受。
- **不必要 `.clone()`**：若 `.clone()` 仅为满足借用检查器而非业务需要，要求作者考虑引用传递或重构所有权；大型集合（`Vec<String>` 等）的无谓克隆是性能陷阱。
- **过度 `unsafe`**：每块 `unsafe` 必须有 `// SAFETY:` 注释说明其安全不变量；缺失注释直接标 HIGH。评估是否有 safe 替代方案。
- **公开 API 无错误类型**：库 crate 公开函数返回 `anyhow::Error` 或裸 `Box<dyn Error>` 而非具名错误枚举，标 MEDIUM（破坏调用方错误处理能力）。
- **阻塞调用混入 async 上下文**：在 `async fn` 中调用 `std::thread::sleep`、同步 I/O 等阻塞调用，标 HIGH（可能饿死 tokio 调度器线程）。

## 安全陷阱

- **整数溢出**：`as` 截断转换（如 `u64 as u32`）在 release 模式下不 panic；审查需要边界保证的转换是否用 `try_from()` 或 `checked_*` 方法。
- **`unsafe` 不变量失效**：指针来源、生命周期延伸、Send/Sync 手动实现——任一条件不满足即 CRITICAL。
- **panic 边界**：库 API 原则上不 panic；会 panic 的条件必须在文档中用 `# Panics` 节说明。
- **未检查索引**：`slice[idx]` 在 idx 越界时 panic；热路径建议 `.get(idx)` 返回 Option。

## 常见缺陷模式

| 模式 | 严重度 | 建议 |
|------|--------|------|
| `Mutex` 持锁跨 `.await` | HIGH | 改用 `tokio::sync::Mutex` 或在 await 前释放锁 |
| 忽略 `#[must_use]` 返回值 | MEDIUM | 显式处理或 `let _ =` 表达有意忽略 |
| 错误类型未实现 `Send + Sync` | MEDIUM | 影响跨线程传递；`thiserror` 自动满足 |
| 循环内重复编译正则 | MEDIUM | 用 `once_cell::sync::Lazy` 缓存 `Regex` |
| 公开 `pub` 字段含内部实现细节 | LOW | 考虑 getter/builder 模式封装 |

## 性能反模式

- 在循环或热路径中调用 `.to_string()` / `.to_owned()` 产生不必要堆分配；改用 `&str` 传递或延迟分配。
- 使用 `format!` 仅为拼接字符串后立即传递给接受 `&str` 的函数；考虑 `write!` 到预分配 `String`。
- 用 `HashMap::new()` 而非 `HashMap::with_capacity(n)` 在已知大小时导致多次 rehash。

## 评审 Checklist

1. `cargo fmt --check` 与 `cargo clippy -- -D warnings` 是否已通过（不在代码中替人跑，而是确认 CI 结果）。
2. 公开 API 是否符合 Rust API Guidelines：类型名 CamelCase，函数名 snake_case，构造函数命名 `new`/`with_*`/`from_*`。
3. 错误类型是否实现 `Debug + Display + Error`；库错误枚举是否 `#[non_exhaustive]`（防止下游 match 被未来变体破坏）。
4. `unsafe` 块是否最小化并附 `// SAFETY:` 注释。
5. 新增公开 API 是否有文档注释（`///`）；会 panic 的函数是否有 `# Panics` 节。
6. 测试是否覆盖正常路径、错误路径、边界值；关键逻辑是否有集成测试。
7. 依赖新增是否必要；是否引入了已有间接依赖的重复功能。
8. `unsafe` / `#[allow(...)]` / `transmute` / 多余 `.clone()` 不是仅为消除编译器报错，而是真正解决了所有权 / 类型问题。
9. 引用的 crate 与 API 真实存在，无虚构的方法或 feature。
