# Rust · 实现编码细则

## 格式化与静态检查

- 提交前必须通过 `cargo fmt --check`（CI 等价检查）；本地开发保存时自动运行 `rustfmt`。
- 运行 `cargo clippy -- -D warnings`：将 clippy 警告视为错误；不得用 `#[allow(...)]` 批量抑制，仅在确有充分理由时加单行 allow 并附注释说明。
- 常见必须处理的 clippy lint：`clippy::unwrap_used`、`clippy::expect_used`（测试代码除外）、`clippy::clone_on_ref_ptr`、`clippy::needless_pass_by_value`。

## 所有权与借用惯例

- 函数参数优先接受引用（`&T` / `&mut T`），仅在需要所有权时接受 `T`（如存入结构体或异步任务）。
- 字符串参数用 `&str`，不用 `&String`；切片参数用 `&[T]`，不用 `&Vec<T>`。
- 结构体字段含有大量克隆开销的类型时，考虑 `Arc<T>` 共享所有权而非深拷贝。
- 避免用 `.clone()` 绕过借用检查器——克隆出现即检查是否存在更好的生命周期或引用方案。

## 错误处理惯用法

- 使用 `?` 运算符在可恢复错误路径上传播，不写 `match err { ... return Err(...) }` 样板。
- **库 crate**：`thiserror` 定义枚举，每个变体附 `#[error("...")]` 消息；用 `#[from]` 自动实现 From 转换。
- **应用 bin**：`anyhow::Result<T>` 作为函数返回类型，`.context()`/`.with_context()` 附加调用位置信息。
- 禁止在库公开 API 中使用 `anyhow::Error`（类型擦除令调用方无法模式匹配错误）。
- `panic!` / `unwrap()` / `expect()` 仅用于：测试、无法恢复的不变量违反、CLI 顶层 main 的快速退出。
- 调用 crate / 标准库 API 前确认方法与签名真实存在，不要凭记忆拼名
- 遇编译器报错应真正解决所有权 / 类型问题，不靠加 `unsafe` / `#[allow(...)]` / 多余 `.clone()` 绕过

## 项目结构

```
my-project/
├── Cargo.toml          # workspace 根（多 crate 时）
├── src/
│   ├── lib.rs          # 库入口（公开 API）
│   ├── main.rs         # 二进制入口（thin wrapper，不含业务逻辑）
│   ├── domain/         # 核心业务逻辑，无 I/O 依赖
│   ├── infra/          # 数据库、HTTP 客户端等外部适配器
│   └── cli/            # CLI 参数解析与命令实现
└── tests/              # 集成测试
```

- `lib.rs` 与 `main.rs` 并存时，main 仅负责解析参数、调用 lib 提供的函数；业务逻辑全部在 lib 侧，方便集成测试覆盖。
- module 可见性默认 `pub(crate)`，仅需跨 crate 公开时才 `pub`。

## 常用标准库与惯用工具

| 需求 | 推荐用法 |
|------|---------|
| 哈希 Map | `std::collections::HashMap`；高性能场景用 `ahash` 或 `indexmap` |
| 序列化 | `serde` + `serde_json` / `serde_yaml`（按格式选 feature） |
| 日期时间 | `chrono` 或 `time` |
| 随机数 | `rand` |
| 正则 | `regex`（注意编译开销，建议 `lazy_static!` 或 `once_cell::sync::Lazy` 缓存） |
| HTTP 客户端 | `reqwest`（async，默认 tokio） |
| 环境变量配置 | `dotenvy` + `envy`（serde 反序列化到结构体） |
