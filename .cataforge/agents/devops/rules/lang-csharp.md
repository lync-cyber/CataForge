# C# · 构建部署细则

## 构建命令

```bash
# 还原依赖（锁定模式）
dotnet restore --locked-mode

# 构建
dotnet build -c Release --no-restore

# 发布（framework-dependent，容器场景）
dotnet publish src/MyApp.Api -c Release -o /app/publish --no-build

# 发布（self-contained，无 runtime 宿主）
dotnet publish src/MyApp.Api -c Release -r linux-x64 --self-contained -o /app/publish
```

- `-c Release` 启用优化并关闭 DEBUG 符号嵌入
- `--no-restore` / `--no-build` 避免重复步骤，CI 中分步执行

## 依赖锁定

- 在 `Directory.Build.props` 或各 csproj 中设置 `<RestorePackagesWithLockFile>true</RestorePackagesWithLockFile>`
- `packages.lock.json` 提交到仓库；CI 中 `--locked-mode` 确保依赖图与锁文件一致，不自动更新
- 依赖升级走独立 PR，不混入功能变更
- 依赖包与基镜像 tag 须确认真实存在的版本，不写臆造版本；改版本后重新 `dotnet restore --locked-mode` 验证锁文件

## CI 缓存策略

- 缓存键：NuGet 全局缓存目录（`~/.nuget/packages`）+ `**/*.csproj` + `**/packages.lock.json` 的哈希
- GitHub Actions 示例：

```yaml
- uses: actions/cache@v4
  with:
    path: ~/.nuget/packages
    key: nuget-${{ hashFiles('**/*.csproj', '**/packages.lock.json') }}
    restore-keys: nuget-
```

- Docker 层缓存：先 `COPY *.csproj` + `dotnet restore`，再 `COPY . .` + `dotnet build`；源码变更不重跑 restore

## 容器基镜像

```dockerfile
# 多阶段构建标准模板
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY ["src/MyApp.Api/MyApp.Api.csproj", "src/MyApp.Api/"]
RUN dotnet restore "src/MyApp.Api/MyApp.Api.csproj" --locked-mode
COPY . .
RUN dotnet publish "src/MyApp.Api" -c Release -o /app/publish --no-build

FROM mcr.microsoft.com/dotnet/aspnet:8.0-jammy-chiseled AS runtime
WORKDIR /app
COPY --from=build /app/publish .
ENTRYPOINT ["dotnet", "MyApp.Api.dll"]
```

| 运行时镜像 | 特点 |
|-----------|------|
| `aspnet:8.0` | 标准 Debian，体积最大，兼容性最好 |
| `aspnet:8.0-jammy-chiseled` | Ubuntu Chiseled（distroless 风格），攻击面最小，体积约缩减 50% |
| `runtime-deps:8.0-jammy-chiseled` + AOT | 无 runtime，仅依赖项；适合 Native AOT 产物 |

- 生产环境优先选 chiseled；chiseled 镜像无 shell，调试需 `dotnet-monitor` sidecar
- 以非 root 用户运行：chiseled 镜像默认 `app` 用户，标准镜像需显式 `USER app`

## 产物发布与版本管理

- SemVer 版本号来源：`Directory.Build.props` 的 `<Version>`；CI 中由 tag 或环境变量注入：

```bash
dotnet build -p:Version=${GITHUB_REF_NAME#v}
```

- NuGet 包发布：`dotnet pack -c Release -o nupkgs` + `dotnet nuget push`
- 镜像 tag 策略：`<registry>/<image>:<semver>` + `latest`（latest 仅指向最新稳定版，不用于生产拉取）
- 健康检查：ASP.NET Core 配置 `/healthz` 端点（`app.MapHealthChecks`），Dockerfile 中 `HEALTHCHECK` 引用
