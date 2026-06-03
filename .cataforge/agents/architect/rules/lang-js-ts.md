# JavaScript / TypeScript · 架构师技术选型细则

## 包与依赖管理

| 工具 | 适用场景 | 权衡 |
|------|---------|------|
| pnpm | 新项目首选 | 硬链接节省磁盘、monorepo workspace 原生支持、安装速度快 |
| npm | 零配置、官方工具链 | 成熟可靠，workspaces 支持完整，大型 monorepo 磁盘占用高 |
| yarn (berry) | 已有存量 yarn 项目 | PnP 模式零 node_modules，但生态兼容性仍有边缘问题 |

锁文件（`package-lock.json` / `pnpm-lock.yaml`）必须提交；CI 用 `npm ci` / `pnpm install --frozen-lockfile` 保证复现性。选型前核实库的当前最新稳定版与维护状态，不沿用记忆中的旧默认；引入依赖前在 npm registry 确认包名真实存在，不要凭记忆写包名（虚构包名会被恶意抢注，即 slopsquatting）。

## 框架分层选项

**前端**

| 框架 | 适用场景 |
|------|---------|
| React + Vite | 生态最广，团队熟悉度高，SPA / 复杂交互 |
| Next.js | SSR / SSG / 全栈一体，SEO 敏感场景 |
| Vue 3 (Composition API) | 渐进式迁移，模板语法学习曲线低 |
| Svelte / SvelteKit | 产物体积极小，轻量交互 |

**后端 / API**

| 框架 | 适用场景 |
|------|---------|
| Fastify | 高吞吐 JSON API，插件体系成熟 |
| Express | 遗留集成、极简场景，生态存量丰富 |
| NestJS | 企业级模块化，DI 容器，团队规模大 |
| Hono | Edge / Cloudflare Workers，极小运行时 |

**运行时**

- Node.js：生态最广，生产首选；LTS 版本追踪。
- Bun：内置打包/测试/TS 转译，本地开发提速显著；生产稳定性仍需评估。
- Deno 2：原生 TS、安全沙箱、Node compat 层；适合工具链脚本。

## 并发与运行模型

1. 事件循环是单线程；CPU 密集型任务（图像处理、加密运算）用 `worker_threads` 卸载。
2. I/O 并发用 `Promise.all` / `Promise.allSettled`；避免串行 `await` 链拖慢吞吐。
3. 流式处理大数据用 Node.js Streams 或 Web Streams API，避免整体加载进内存。

## 类型系统与边界

- `tsconfig.json` 开启 `"strict": true`（含 `noUncheckedIndexedAccess` 推荐补充）。
- 外部输入（HTTP 请求体、环境变量、文件解析）必须经运行时校验（`zod` / `valibot`），不可只依赖 TypeScript 类型。
- 避免 `any`；需要逃生时用 `unknown` + 类型收窄。

## 构建产物形态

- 库：双格式输出 ESM + CJS（`tsup` / `unbuild` 自动处理），`package.json` 用 `exports` 字段声明入口。
- 前端应用：默认 ESM；用 `Vite` / `esbuild` 打包；生产构建开启 code splitting 与 tree-shaking。
- Node 服务：直接运行 TS 源码（`tsx` / `ts-node`）仅限开发；生产编译为 CJS 或 ESM 并固化 `dist/`。
