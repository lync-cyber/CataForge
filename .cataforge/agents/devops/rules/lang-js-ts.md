# JavaScript / TypeScript · 构建部署细则

## 构建与打包工具

| 工具 | 适用场景 |
|------|---------|
| Vite | 前端 SPA / MPA，开发服务器 HMR 快 |
| tsup | 库打包，零配置 ESM + CJS 双格式输出 |
| esbuild | 超大型项目或自定义管线，直接调用 API |
| Rollup | 需要精细 tree-shaking 的库 |
| Next.js 内置 | Next.js 项目不额外引入打包工具 |

生产构建启用 `sourcemap: false`（或上传到错误追踪服务后删除）；开启 minify 与 tree-shaking；chunk splitting 按路由或动态 `import()` 自动分割。

## 依赖锁定

- 锁文件（`package-lock.json` / `pnpm-lock.yaml`）必须提交并纳入 PR diff 审查。
- CI 安装命令：`npm ci` / `pnpm install --frozen-lockfile`，禁止裸 `npm install`。
- 定期运行 `npm audit --audit-level=high`，高危漏洞阻塞流水线。
- 依赖与基镜像 tag 须确认真实存在的版本，不写 `latest` 或臆造版本；改 `package.json` 版本后重新生成锁文件并 `npm ci` 验证

## CI 缓存策略

```yaml
# GitHub Actions 示例骨架
- uses: actions/cache@v4
  with:
    path: ~/.pnpm-store   # pnpm 全局缓存
    key: pnpm-${{ hashFiles('pnpm-lock.yaml') }}
    restore-keys: pnpm-
```

- 缓存键包含锁文件哈希；锁文件变动自动失效，无需手动清缓存。
- `node_modules` 不缓存（体积大、平台相关）；缓存包管理器的全局 store 即可。
- TypeScript 增量编译缓存（`.tsbuildinfo`）可单独缓存，加速类型检查步骤。

## 容器基镜像

```dockerfile
# 构建阶段
FROM node:22-slim AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

# 运行阶段
FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
USER node
CMD ["node", "dist/index.js"]
```

- 优先 `node:<lts>-slim`；安全要求高时用 `gcr.io/distroless/nodejs22`（无 shell）。
- 不以 root 运行；生产镜像不包含 devDependencies 和源代码。

## 产物发布与版本管理

- 遵循 SemVer；通过 Conventional Commits 驱动自动化版本号（`semantic-release` / `changesets`）。
- `npm publish` 前检查 `package.json` 的 `files` 字段，仅发布 `dist/` 和必要类型文件。
- 发布 scoped 包（`@org/pkg`）时确认 `publishConfig.access: "public"` 或私有 registry 配置。
- tag 命名：`v<major>.<minor>.<patch>`；在 CI 的发布 job 中自动打 tag，不手动推送。
