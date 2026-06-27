# Rust · 架构师技术选型细则

## 依赖管理

- 使用 `Cargo.toml` 的 `[features]` 声明可选依赖，避免默认拉入非必要传递依赖。
- workspace 多 crate 项目在根 `Cargo.toml` 统一声明 `[workspace.dependencies]`，子 crate 以 `workspace = true` 继承，避免版本漂移。
- 评估第三方 crate 时查看下载量趋势、维护频率、`unsafe` 用量（`cargo-geiger`）；优先选 crates.io 生态主流、无过多不必要 unsafe 的依赖。
- 生产项目提交 `Cargo.lock`；库不提交（`.gitignore` 排除）。
- 选型前核实 crate 的当前版本与维护状态，不沿用记忆中的旧默认；引用的 crate 与 feature 须在 crates.io 确认真实存在，不要凭记忆拼写

## Web 框架选型

| 场景 | 首选 | 备选 | 权衡要点 |
|------|------|------|---------|
| 新建 API 服务 | `axum` 0.8+ | `actix-web` 4 | axum 与 Tower/Tokio 生态无缝集成，中间件可复用；actix-web 原始吞吐量更高，适合极致性能场景 |
| 极高并发吞吐 | `actix-web` | `axum` | actix-web 经过更多生产大流量验证 |
| CLI 工具 | `clap` 4 | `argh` | clap derive 宏减少样板，功能全面；argh 更轻量 |
| gRPC 服务 | `tonic` | — | 基于 tokio，与 axum 同生态 |

## 异步运行时

- 默认选用 `tokio`（多线程调度器 `#[tokio::main]`）；`async-std` 仅在兼容性有硬性要求时考虑。
- 避免混用两套运行时；运行时选择在 workspace 根层面统一。
- 阻塞 I/O 或 CPU 密集任务使用 `tokio::task::spawn_blocking`，不在 async 上下文直接调用阻塞调用。

## 并发与所有权模型

- 线程安全边界通过 `Send + Sync` trait 由编译器保证，架构文档说明跨线程共享数据的结构（`Arc<Mutex<T>>` vs 消息传递 `mpsc`）。
- 优先消息传递（channel）隔离可变状态；`Arc<RwLock<T>>` 适合读多写少的共享缓存。
- Actor 模型考虑 `tokio::sync::mpsc` 手写或 `actix` actor 框架；无需强依赖 actor 框架。

## 类型系统与错误边界

- **库 crate**：用 `thiserror` 定义具名错误枚举，让调用方可以模式匹配不同错误变体。
- **应用 crate / bin**：用 `anyhow::Result` 快速传播，减少样板；结合 `.context("...")` 附加上下文。
- 公开 API 返回类型用 `Result<T, YourError>`，避免 `panic` 作为控制流。
- 跨 crate 边界的 trait 对象错误用 `Box<dyn std::error::Error + Send + Sync>`。

## 构建产物形态

| 目标 | 方法 | 说明 |
|------|------|------|
| 静态二进制 | `--target x86_64-unknown-linux-musl` | 无 glibc 依赖，可放入 scratch/distroless |
| 动态库 | `crate-type = ["cdylib"]` | FFI / WASM 输出 |
| WebAssembly | `wasm-pack` / `wasm-bindgen` | 浏览器或 WASI 目标 |
| 交叉编译 | `cross` crate + Docker 工具链 | 简化多平台构建 |

- release profile 默认开启 `lto = "thin"`、`codegen-units = 1` 获得更优二进制体积与性能；首次构建耗时增加是已知代价。
