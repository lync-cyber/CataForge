# C# · 测试编写细则

## 主流测试框架

| 框架 | 适用场景 | 特点 |
|------|---------|------|
| **xUnit** | 新项目首选 | 构造函数 setup，无共享静态状态，[Theory] 参数化 |
| **NUnit** | 已有 NUnit 体系的团队 | [SetUp]/[TearDown] 显式，约束模型断言 |

测试项目以 `.Tests` 后缀命名，`<IsPackable>false</IsPackable>`；不建议在生产 csproj 内写测试。

## 断言风格

优先使用 **FluentAssertions** 提升可读性，失败信息包含上下文：

```csharp
result.Should().Be(42);
items.Should().HaveCount(3).And.Contain(x => x.IsActive);
act.Should().ThrowAsync<InvalidOperationException>()
   .WithMessage("*not found*");
```

不使用裸 `Assert.Equal` 时错误信息仅显示预期/实际值，缺少语境。

## Setup 模式

```csharp
// xUnit：构造函数负责 setup，IClassFixture<T> 共享重量级资源
public class OrderServiceTests : IClassFixture<DatabaseFixture>
{
    private readonly OrderService _sut;

    public OrderServiceTests(DatabaseFixture db)
    {
        _sut = new OrderService(db.Context);
    }
}
```

- `IAsyncLifetime` 用于需要 `async` 的 setup/teardown
- 集成测试用 `WebApplicationFactory<TProgram>` 启动内存 HTTP 服务

## 参数化测试

```csharp
[Theory]
[InlineData(0, false)]
[InlineData(1, true)]
[InlineData(-1, false)]
public void IsPositive_ReturnsExpected(int value, bool expected)
{
    Calculator.IsPositive(value).Should().Be(expected);
}

// 复杂数据用 MemberData / ClassData
```

## Mock 库

| 库 | 语法风格 | 适用场景 |
|----|---------|---------|
| **Moq** | `new Mock<IRepo>()` + `Setup().Returns()` | 主流选择，生态最广 |
| **NSubstitute** | `Substitute.For<IRepo>()` + `Returns()` | 更简洁，BDD 风格 |

最小骨架：

```csharp
var repo = new Mock<IOrderRepository>();
repo.Setup(r => r.GetByIdAsync(1, It.IsAny<CancellationToken>()))
    .ReturnsAsync(new Order { Id = 1 });

var sut = new OrderService(repo.Object);
var result = await sut.GetOrderAsync(1);

result.Should().NotBeNull();
repo.Verify(r => r.GetByIdAsync(1, It.IsAny<CancellationToken>()), Times.Once);
```

## 覆盖率

- 使用 **coverlet.collector**（NuGet）收集覆盖率：

```bash
dotnet test --collect:"XPlat Code Coverage"
```

- CI 中生成报告：`reportgenerator -reports:**/coverage.cobertura.xml -targetdir:coverage-report`
- 设置覆盖率门槛（`runsettings` 中 `<Threshold>`）；目标 80% 行覆盖率作为基线
- 单元测试、集成测试分开跑，单元测试不依赖外部服务（数据库、网络）
- 断言须能真正失败，避免只 `result.Should().NotBeNull()` 的空壳；补边界与异常路径（`ThrowAsync`），不要只测正常输入
