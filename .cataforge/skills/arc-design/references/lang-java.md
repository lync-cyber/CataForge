# Java · 架构师技术选型细则

## 构建与依赖管理

| 工具 | 适用场景 | 权衡 |
|------|---------|------|
| Maven | 企业/团队标准化；插件生态成熟；约定优于配置 | XML 冗长；增量构建不如 Gradle |
| Gradle | 多模块大型项目；Android；需要脚本化构建逻辑 | 学习曲线高；daemon 内存开销 |

推荐：团队无既有偏好时优先 Maven（可预期性强）；多模块 monorepo 或需精细 task 依赖时选 Gradle。选型前核实依赖的当前版本与维护状态，不沿用记忆中的旧默认；引用的库与 API（groupId:artifactId、方法签名）须确认真实存在，不要凭记忆拼写。

## 主流框架选项

**Web 层**

| 框架 | 定位 | 权衡 |
|------|------|------|
| Spring Boot | 生态最完整，企业标准 | 启动慢、内存高；适合长生命周期服务 |
| Quarkus | 云原生、GraalVM 原生镜像友好，启动极快 | 部分 Spring 扩展不兼容，社区较小 |
| Micronaut | 编译期 DI，无反射；适合微服务/FaaS | 生态窄，调试信息较少 |

**数据层**

| 库 | 定位 | 权衡 |
|----|------|------|
| Spring Data JPA / Hibernate | ORM 全功能，JPQL/Criteria API | N+1 风险高，复杂查询难以优化 |
| jOOQ | 类型安全 SQL DSL，贴近原生 SQL | 需代码生成，学习曲线中等 |
| MyBatis | XML/注解 SQL 映射，灵活性高 | 无类型安全，手写 SQL 维护成本 |

选型准则：CRUD 主导且团队熟悉 ORM → JPA；复杂报表/分析查询 → jOOQ；已有 SQL 资产且需精细控制 → MyBatis。

## 并发与运行模型

- **线程池（ExecutorService）**：I/O 密集型传统方案；`ForkJoinPool.commonPool()` 用于 CPU 并行任务
- **CompletableFuture**：异步编排，适合少量并发链式调用；`thenCompose` / `thenCombine` 组合
- **虚拟线程（Project Loom，Java 21 GA）**：`Thread.ofVirtual()` / `Executors.newVirtualThreadPerTaskExecutor()`；阻塞 I/O 场景吞吐大幅提升，代码同步写法；**不适合** CPU 密集段（需 carrier 线程隔离）
- **Reactive（Reactor / RxJava）**：背压场景或已有响应式栈时引入；否则虚拟线程通常更简单

## 类型系统与边界

- **record**（Java 16+）：不可变数据载体，自动 equals/hashCode/toString；优先替代 POJO DTO
- **sealed class / interface**（Java 17+）：有限层级的代数类型；配合 `switch` 模式匹配（Java 21）做穷举
- **Optional**：用于方法返回值表达"可能为空"；不用于字段、参数或集合元素
- **泛型边界**：公共 API 使用有界通配符（`? extends T` / `? super T`）；内部实现优先具体类型

## 构建产物形态

| 产物 | 场景 | 工具 |
|------|------|------|
| 可执行 fat-jar | 服务端部署，最通用 | `spring-boot-maven-plugin` / `shadow` |
| 分层 JAR（Layered） | 容器构建缓存优化 | Spring Boot 分层 jar 支持 |
| GraalVM native image | 极低内存/启动时间（FaaS、CLI） | `native-maven-plugin` / Quarkus 原生构建 |
| 普通 JAR（库） | 发布 Maven Central | `maven-jar-plugin` + sources + javadoc |
