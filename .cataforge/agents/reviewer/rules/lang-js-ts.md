# JavaScript / TypeScript · 代码评审细则

## 典型坏味道

1. **`any` 滥用**：`any` 绕过类型检查，等同关闭 TS 保护；要求改 `unknown` + 收窄，或补充 `zod` 校验。
2. **`==` 而非 `===`**：宽松相等引发隐式类型转换；一律用严格相等，ESLint `eqeqeq` 规则强制。
3. **未处理的 Promise**：裸 `promise.then()` 不接 `.catch()`，或 `async` 函数调用结果被丢弃（`no-floating-promises`）。
4. **`console.log` 遗留**：生产代码用结构化 logger，不留调试 log；ESLint `no-console` 在 src/ 下开启。
5. **大型 if-else 链替代多态**：超过 4 个分支的类型分发考虑策略对象或 Map dispatch。

## 安全陷阱

| 风险 | 检查点 |
|------|-------|
| XSS | 前端避免 `innerHTML` / `dangerouslySetInnerHTML`；输出到 DOM 用 `textContent` 或 DOMPurify |
| 原型污染 | 禁止 `obj[key] = value` 形式的动态键赋值（key 来自外部）；深合并用 `structuredClone` 或白名单键 |
| `eval` / `new Function` | 任何字符串执行路径均拒绝；存在时要求说明强制必要性 |
| 依赖供应链 | 新增依赖检查 `npm audit` / Snyk；关注下载量极低或维护者单人依赖 |
| 敏感信息硬编码 | 密钥/Token 必须走环境变量；grep 检查 `process.env` 之外出现的 API key 字样 |

## 常见缺陷模式

- **异步竞态**：多个并发 `setState` / 写共享变量，需加锁或用 `AbortController` 取消旧请求。
- **内存泄漏**：事件监听器、定时器、Observable 订阅未在组件卸载或对象销毁时清除。
- **可选链滥用**：`a?.b?.c?.d` 掩盖了真正的"此路径不应为空"逻辑；中间层为空应报错而非静默 `undefined`。
- **类型断言越权**：`as` 强转绕过类型检查，审查 `as unknown as T` 的每一处。

## 性能反模式

- 在渲染热路径（React render / Vue setup 每次重算）内创建新对象/数组——应 `useMemo` / `computed` 缓存。
- `Array.find` 后再 `Array.map`——合并为单次遍历。
- 大量同步 I/O（`fs.readFileSync` 在请求处理路径中）——换异步版本。
- 未分页的大集合全量加载到内存。

## 评审 Checklist

- [ ] 所有外部输入（HTTP body、URL 参数、文件内容）经运行时校验
- [ ] 无 `any`，或有充分注释说明的豁免
- [ ] 所有 Promise/async 调用有明确错误处理
- [ ] 新增依赖已通过安全扫描，版本固定
- [ ] 无原型污染向量（动态键写入）
- [ ] 无生产环境 `console.log` / 调试代码
- [ ] 单元测试覆盖新增公共函数的核心分支
- [ ] 第三方 npm 包与 API 真实存在，无虚构包名（slopsquatting）或方法
- [ ] 依赖版本与调用未使用已弃用写法
