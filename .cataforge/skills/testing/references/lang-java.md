# Java · 测试编写细则

## 框架与工具栈

- 测试框架：**JUnit 5**（Jupiter）
- 断言库：**AssertJ**（流式 API，失败信息清晰）
- Mock 框架：**Mockito**（`mockito-junit-jupiter` 集成）
- 覆盖率：**JaCoCo**（`mvn verify` 生成报告）；典型行覆盖基线 80%

最小依赖（Maven）：
```xml
<dependency>
  <groupId>org.junit.jupiter</groupId>
  <artifactId>junit-jupiter</artifactId>
  <scope>test</scope>
</dependency>
<dependency>
  <groupId>org.assertj</groupId>
  <artifactId>assertj-core</artifactId>
  <scope>test</scope>
</dependency>
<dependency>
  <groupId>org.mockito</groupId>
  <artifactId>mockito-junit-jupiter</artifactId>
  <scope>test</scope>
</dependency>
```

## 断言风格

使用 AssertJ 而非 JUnit 原生断言（`assertEquals`），失败时输出更丰富：

```java
import static org.assertj.core.api.Assertions.*;

assertThat(result).isEqualTo("expected");
assertThat(list).hasSize(3).contains("a", "b");
assertThatThrownBy(() -> service.process(null))
    .isInstanceOf(IllegalArgumentException.class)
    .hasMessageContaining("must not be null");
```

## Setup 与 Teardown

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    OrderRepository repository;

    @InjectMocks
    OrderService service;

    @BeforeEach
    void setUp() {
        // 每个测试前重置状态
    }

    @AfterAll
    static void tearDownAll() {
        // 模块级资源清理（如测试容器）
    }
}
```

- `@BeforeEach` 做轻量状态初始化；`@BeforeAll`（static）用于昂贵的单次启动（数据库、容器）
- 测试间禁止共享可变状态

## 参数化测试

```java
@ParameterizedTest
@CsvSource({
    "hello, HELLO",
    "'',    ''",
    "  ,    '  '",
})
void testToUpperCase(String input, String expected) {
    assertThat(StringUtils.toUpper(input)).isEqualTo(expected);
}

@ParameterizedTest
@MethodSource("invalidInputs")
void rejectsInvalidInput(String input) {
    assertThatThrownBy(() -> service.process(input))
        .isInstanceOf(IllegalArgumentException.class);
}

static Stream<String> invalidInputs() {
    return Stream.of(null, "", "  ");
}
```

## Mock 使用规范

```java
// given
when(repository.findById(1L)).thenReturn(Optional.of(new Order(1L, "PENDING")));

// when
Order result = service.getOrder(1L);

// then
assertThat(result.status()).isEqualTo("PENDING");
verify(repository).findById(1L);
verifyNoMoreInteractions(repository);
```

- mock 外部依赖（Repository、HTTP 客户端、消息队列）；不 mock 被测单元内部
- 集成测试用 **Testcontainers** 替代 H2 内存库，保证与生产环境数据库行为一致

## 测试命名与分层

- 命名：`<被测方法>_<场景>_<期望结果>`，如 `findById_whenNotFound_throwsException`
- 单元测试：`src/test/java/.../OrderServiceTest.java`
- 集成测试：`src/test/java/.../OrderRepositoryIT.java`（`IT` 后缀，Maven Failsafe 插件执行）
- 覆盖率报告路径：`target/site/jacoco/index.html`
- 断言须能真正失败，避免只 `assertThat(x).isNotNull()` 的空壳；补边界与异常路径（`assertThatThrownBy`），不要只测正常输入
