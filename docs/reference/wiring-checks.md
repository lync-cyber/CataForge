# Wiring 检查 — 按语言细则

> code-review §integration-wiring 与 tech-lead §production-path AC 引用的具体语言识别模式。skill / agent 主体保持语言无关，本文档承载语言特定的反例与正则候选。
>
> 新增语言时在 §对应小节增条；正则候选同步到 `cataforge.skill.builtins.code_review.rules.wiring-{lang}.yaml`（package default）或 `<project>/.cataforge/skills/code-review/rules/wiring-{lang}.yaml`（project override）。

## 1. 通用判定

不论语言，"wiring 落地"的判据三段：

1. **接线对象的字面调用点存在于生产路径（src/、app/、lib/ 等非测试目录）**
2. 仅 tests/ 内构造调用、mock 注入、fixture 中实例化 — **不算落地**
3. 任务卡显式声明 `wiring_placeholder: true` + 关联 backlog ID — 豁免，但 reviewer 必须在审查报告链接 backlog

## 2. JavaScript / TypeScript（前端 / Node 后端）

### 2.1 空 handler 占位

`onXxx` / `on*` 事件 prop 的取值不能是以下三种：

| 反例 | 说明 |
|---|---|
| `() => {}` | 空 arrow body |
| `() => null` | 仅 return null |
| `() => undefined` | 仅 return undefined |

正则候选：`cataforge.skill.builtins.code_review.rules.wiring-js-ts.yaml`

### 2.2 prop 链路终点

声明了 `consumer_components: [<List>]` 的组件，其 prop 接受方必须将 prop 转发到具体业务调用（store action / API client / router push），不能仅在 destructure 后弃用。

### 2.3 store action 落地

Redux / Zustand / Pinia 等 store 模式：action creator 定义后必须在 `dispatch(action(...))` / `store.action(...)` 形式被消费组件调用，仅在 reducer / store 内部定义不算落地。

## 3. Python（后端 / CLI / 数据管道）

### 3.1 DI 容器注册

`Container.{provider_name} = providers.Singleton(<Class>)` / `inject.Binder.install(...)` / `@injector.provider` 等注册写法必须有 **生产路径的取值点**。仅 tests/ 内 `container.{name}()` 取值或 fixture 覆盖不算落地。

反例：`src/app/di.py` 定义 `IngestTasks` provider，但 `src/app/main.py` / `src/app/api/` 没有 `container.ingest_tasks()` 取值。

### 3.2 signal handler 绑定

Django / Blinker / PyDispatch / Qt signal — handler 函数必须有 `signal.connect(<handler>)` 或 `@signal.receiver` 装饰器声明。

反例：`src/app/signals.py` 定义 `on_user_created(sender, instance, ...)`，但全仓没有 `post_save.connect(on_user_created, sender=User)`。

### 3.3 lifespan / startup / shutdown hook

FastAPI / Starlette — hook 函数必须挂到 `app.router.lifespan_context` 或 `app.add_event_handler("startup", <fn>)` / `app.add_event_handler("shutdown", <fn>)`。

反例：`src/app/lifecycle.py` 定义 `async def warmup_cache(app)`，但 `src/app/main.py` 没有 `app.add_event_handler("startup", warmup_cache)` 或在 `lifespan_context` 中调用。

### 3.4 CLI 子命令注册（Click / Typer / argparse）

`@cli.command(...)` / `@app.command(...)` 装饰的函数必须挂到顶层 `cli` / `app` group，子 group 须被父 group `add_command` 引入。仅在 tests 里 `runner.invoke(<cmd>)` 不算落地。

## 4. Go / Rust / Java（占位）

按 §2-3 风格逐步补：

- **Go**：goroutine 启动点 / channel 消费侧 / `http.HandleFunc` 路由注册
- **Rust**：`tokio::spawn(...)` 接线点 / `axum::Router.route(...)` 注册 / trait impl 在生产路径被实例化
- **Java**：`@Bean` / `@Component` / `@Autowired` 在 Spring context scan path 内 / `EventBus.register(...)` 落地

## 5. 引用关系

- code-review SKILL §Step 2 `integration-wiring` 维度
- tech-lead AGENT §Execution Rules `production-path AC`
- agent-result schema `wiring_complete` / `wiring_evidence` 字段
