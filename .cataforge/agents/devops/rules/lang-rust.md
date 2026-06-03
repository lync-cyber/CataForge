# Rust · 构建部署细则

## 构建

- **开发构建**：`cargo build`（debug profile，包含 debug info，不优化）。
- **生产构建**：`cargo build --release`。在 `Cargo.toml` 中为 release profile 添加：
  ```toml
  [profile.release]
  lto = "thin"          # 链接时优化，平衡构建速度与二进制体积
  codegen-units = 1     # 更彻底的内联优化
  strip = true          # 剥离 debug symbol，减小二进制体积
  ```
- 交叉编译推荐 `cross` crate：`cross build --target aarch64-unknown-linux-musl --release`，内部用 Docker 管理工具链，无需手动配置 linker。

## 依赖锁定

- 应用/服务：提交 `Cargo.lock`，确保 CI 与生产环境使用完全相同的依赖树。
- 库 crate：`.gitignore` 排除 `Cargo.lock`；下游消费者自行解析兼容版本。
- 定期运行 `cargo update` + 全量测试，主动跟进依赖更新；`cargo audit` 检查已知安全漏洞。
- 新增 crate 与基镜像 tag 前核对真实存在的版本，不写臆造版本或 crate 名

## CI 缓存策略

- **GitHub Actions**：使用 `Swatinem/rust-cache` action，自动缓存 `~/.cargo/registry`、`~/.cargo/git`、`target/` 目录，按 `Cargo.lock` hash 失效。
- **sccache**：设置 `RUSTC_WRAPPER=sccache`，将编译单元结果缓存到本地磁盘或 S3，跨 CI job 共享编译缓存；适合大型 workspace 或自托管 CI。
- 矩阵构建（多目标/多 toolchain）时各维度独立缓存键，避免缓存污染。

## 容器化（多阶段构建）

推荐两阶段 Dockerfile：

```dockerfile
# 阶段 1：构建（musl 静态链接）
FROM rust:1-alpine AS builder
RUN apk add --no-cache musl-dev
WORKDIR /app
COPY . .
RUN cargo build --release --target x86_64-unknown-linux-musl

# 阶段 2：最小运行镜像
FROM scratch
COPY --from=builder /app/target/x86_64-unknown-linux-musl/release/myapp /myapp
ENTRYPOINT ["/myapp"]
```

- musl 静态链接产物可放入 `scratch`（零依赖）；若需 CA 证书或 /tmp 等，改用 `gcr.io/distroless/static`。
- 若无法使用 musl（如依赖含 C FFI 库），改用 `distroless/cc` 作为运行镜像。
- 使用 `cargo-chef` 预先缓存依赖编译层，避免每次源码变更重新编译所有依赖。

## 产物发布与版本管理

- 版本号遵循 SemVer：`MAJOR.MINOR.PATCH`；breaking change 升 MAJOR。
- **库发布到 crates.io**：`cargo publish --dry-run` 验证后 `cargo publish`；确保 `Cargo.toml` 填写 `license`、`description`、`repository`。
- **二进制发布**：使用 `cargo-dist` 自动生成跨平台 GitHub Release 产物（静态二进制 + 校验和 + 安装脚本）；在 `dist-workspace.toml` 声明目标 triple。
- 打 tag 触发 CI 发布：`git tag v1.2.3 && git push origin v1.2.3`。

## 工具链管理

- 在仓库根放置 `rust-toolchain.toml`（或 `rust-toolchain`）锁定 toolchain 版本，确保团队与 CI 使用相同编译器：
  ```toml
  [toolchain]
  channel = "stable"
  components = ["rustfmt", "clippy"]
  ```
