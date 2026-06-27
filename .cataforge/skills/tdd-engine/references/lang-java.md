# Java · 实现编码细则

## 格式化与 Lint

- 格式化：**google-java-format**（或 **Spotless** 插件封装）；统一 `--aosp` 或默认风格，写入 Maven/Gradle 构建
- Lint：**Checkstyle**（样式）+ **SpotBugs**（潜在 bug）+ **Error Prone**（编译期分析）

最小 Spotless 配置（Maven `pom.xml` 片段）：
```xml
<plugin>
  <groupId>com.diffplug.spotless</groupId>
  <artifactId>spotless-maven-plugin</artifactId>
  <configuration>
    <java>
      <googleJavaFormat/>
      <removeUnusedImports/>
    </java>
  </configuration>
</plugin>
```

CI 中跑 `mvn spotless:check checkstyle:check spotbugs:check`；本地可 `mvn spotless:apply` 自动修复格式。

## 命名与可见性惯例

- 类名 `UpperCamelCase`；方法、变量 `lowerCamelCase`；常量 `UPPER_SNAKE_CASE`
- 包名全小写，反向域名（如 `com.example.order.domain`）
- 访问修饰符最小化：能 `private` 就不 `protected`，能 `package-private` 就不 `public`
- 接口命名描述能力而非实现（`UserRepository` 而非 `IUserRepository`）

## 错误处理惯用法

- **受检异常（checked）**：仅用于调用方能够合理恢复的场景（如 `IOException`）；框架层通常包装为运行时异常
- **非受检异常（unchecked）**：业务域错误（`IllegalArgumentException`、自定义 `DomainException`）默认继承 `RuntimeException`
- **try-with-resources**：所有实现 `AutoCloseable` 的资源（连接、流、文件）必须用此语法；禁止在 `finally` 手动 `close()`
- **Optional 处理**：用 `orElseThrow()` / `map()` 链式处理；禁止 `isPresent()` + `get()` 配对（等同于 null check 的劣化写法）
- 跨层传播时用 `throw new AppException("ctx", cause)` 保留原因链（`initCause` / 构造器传 `Throwable`）

## 项目结构

推荐**领域分包**而非技术分包：
```
src/main/java/com/example/
├── order/
│   ├── OrderController.java
│   ├── OrderService.java
│   ├── OrderRepository.java
│   └── Order.java           ← record / entity
├── user/
└── shared/
    └── exception/
```

- 每个顶级包对应一个业务域；跨域依赖通过接口隔离
- 测试目录镜像主目录：`src/test/java/com/example/order/OrderServiceTest.java`

## 常用标准库与惯用工具

| 需求 | 推荐 |
|------|------|
| 集合操作 | `Stream` API（filter/map/collect）；批量转换用 `Collectors.toUnmodifiableList()` |
| 日期时间 | `java.time`（`LocalDate` / `ZonedDateTime` / `Instant`）；禁止 `java.util.Date` / `Calendar` |
| 不可变集合 | `List.of()` / `Map.of()` / `Set.copyOf()`（Java 9+）|
| 字符串处理 | `String.formatted()` / `StringBuilder`；循环拼接禁用 `+`  |
| 数值 | `BigDecimal` 处理货币；禁止 `float/double` 做精确计算 |
| 并发工具 | `java.util.concurrent`（`ConcurrentHashMap`、`AtomicLong`、`CountDownLatch`）|

调用标准库 / 第三方 API 前确认方法与签名真实存在，不要凭记忆拼名；对可能为 null 的外部数据显式处理（`Objects.requireNonNull` 或 `Optional`），不要假设数据总是存在。
