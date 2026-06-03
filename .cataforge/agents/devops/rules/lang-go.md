# Go · 构建部署细则

## 本地构建

- 标准构建命令：`go build -o bin/app ./cmd/app`。
- 注入版本信息使用 `ldflags`：

  ```bash
  go build -ldflags="-X main.Version=${VERSION} -X main.Commit=${GIT_COMMIT}" ./cmd/app
  ```

- 纯静态产物（容器友好）：`CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build ...`。
- 交叉编译通过 `GOOS` / `GOARCH` 环境变量控制，无需额外工具链。

## 依赖锁定

- `go.sum` 必须提交版本控制，确保可重现构建。
- 使用 `vendor/` 目录时，`go mod vendor` 生成后提交；CI 用 `go build -mod=vendor`。
- 不使用 vendor 时，CI 需配置模块代理（`GOPROXY`）和缓存（见下方）。
- 依赖版本与基镜像 tag 须确认真实存在，不写臆造版本；module path（含 `/vN` 后缀）凭来源核对，不靠记忆拼写

## CI 缓存策略

- 缓存路径：`$(go env GOMODCACHE)`（模块缓存）和 `$(go env GOCACHE)`（构建缓存）。
- 缓存 key 绑定 `go.sum` 哈希，`go.sum` 变更时自动失效。
- GitHub Actions 示例：

  ```yaml
  - uses: actions/cache@v4
    with:
      path: |
        ~/.cache/go/pkg/mod
        ~/.cache/go/build
      key: go-${{ hashFiles('go.sum') }}
  ```

## 容器基镜像

多阶段构建是 Go 容器化的标准做法：

```dockerfile
FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /app/server ./cmd/app

FROM gcr.io/distroless/static-debian12
COPY --from=builder /app/server /server
ENTRYPOINT ["/server"]
```

- 无 CGO 时优先使用 `scratch` 或 `distroless/static`，镜像体积最小且攻击面最低。
- 需要 CA 证书时用 `distroless/base` 或 `alpine`（加 `ca-certificates`）。

## 产物发布与版本管理

- 版本号遵循 SemVer（`vMAJOR.MINOR.PATCH`），tag 格式 `v1.2.3`。
- 多平台二进制发布推荐 `goreleaser`：`.goreleaser.yaml` 声明目标平台、归档格式和 Changelog 生成规则，CI 在 tag push 时触发 `goreleaser release`。
- Go 模块版本 ≥ v2 时，`go.mod` 的 module path 必须以 `/v2` 结尾（`module github.com/org/repo/v2`）。
