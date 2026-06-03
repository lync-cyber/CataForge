# Rust · 调试诊断细则

## 主流调试器

| 工具 | 适用场景 | 说明 |
|------|---------|------|
| `rust-lldb` / `lldb` | macOS / Linux | Rust 原生调试体验最佳；自带 Rust 类型美化打印 |
| `rust-gdb` / `gdb` | Linux | 随 Rust toolchain 附带，包含 Rust pretty-printer |
| VS Code + `CodeLLDB` 插件 | 图形调试 | 断点、变量查看、条件断点；`.vscode/launch.json` 配置 `"type": "lldb"` |
| `cargo test -- --nocapture` | 测试调试 | 打印测试中的 stdout；结合 `eprintln!` 快速检查中间状态 |

调试构建必须用 debug profile（不加 `--release`），确保 debug symbol 存在。

## Panic Backtrace 解读

```bash
RUST_BACKTRACE=1 cargo run          # 精简 backtrace（过滤标准库帧）
RUST_BACKTRACE=full cargo run       # 完整 backtrace（含所有帧）
```

- backtrace 从下往上读：最底层是 `main` / tokio runtime 入口，越往上越接近 panic 点。
- 关注首个出现在 `src/` 路径的帧，即业务代码 panic 位置。
- release 构建默认剥离 symbol（`strip = true`）；若需在 release 下保留 backtrace，临时在 profile 加 `debug = true`。

## 常见错误定位

**编译期错误（borrow checker / lifetime）：**
1. 阅读 `error[EXXXX]` 提示，`rustc --explain EXXXX` 获取详细说明与示例。
2. 生命周期错误优先检查：函数签名是否缺少显式生命周期标注、返回引用的 lifetime 是否与输入绑定。
3. `cannot borrow ... as mutable because it is also borrowed as immutable`：检查可变引用与不可变引用的作用域重叠，缩短不可变引用生命周期或重构获取顺序。

**运行时错误：**
1. `thread 'main' panicked at 'index out of bounds'`：检查所有数组 / 切片直接索引，改用 `.get()` 返回 Option。
2. `called Option::unwrap() on a None value`：追踪产生 None 的源头，加 `.ok_or(...)` 或 `?` 传播。
3. Deadlock（tokio 环境）：检查是否跨 `.await` 持有 `std::sync::Mutex`；改用 `tokio::sync::Mutex`。

借用 / 生命周期报错先 `rustc --explain EXXXX` 理解再修，不靠盲加 `.clone()` / `unsafe` 消错；每个修复配能复现原 bug 的回归测试，确认改前失败、改后通过。

## 日志与结构化追踪

- 生产代码使用 `tracing` crate（`tracing::info!`、`tracing::error!` 等），不用 `println!`。
- 在 main 初始化 subscriber：`tracing_subscriber::fmt::init()`（开发）或 JSON 格式（生产）。
- `RUST_LOG=debug cargo run` 控制日志级别；`RUST_LOG=my_crate=trace,hyper=warn` 细化模块级别。
- span 覆盖 async 任务时用 `#[tracing::instrument]` 宏自动记录入参与执行时长。

## Profiling

- **火焰图**：`cargo install flamegraph`，然后：
  ```bash
  CARGO_PROFILE_RELEASE_DEBUG=true cargo flamegraph --bin myapp
  ```
  生成 `flamegraph.svg`，浏览器打开交互查看调用栈热点。
- **perf（Linux）**：`sudo perf record -g -F 99 -- ./target/release/myapp`，结合 `perf report` 查看函数级耗时。
- **samply**：跨平台采样 profiler，`cargo install samply`，`samply record ./target/release/myapp`；输出可在 Firefox Profiler 可视化。
- **内存**：`valgrind --tool=massif`（Linux）或 `heaptrack` 追踪堆分配；Rust 无 GC，内存泄漏通常来自 `Arc` 循环引用或全局 `static` 持有数据。
