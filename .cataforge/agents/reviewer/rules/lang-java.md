# Java · 代码评审细则

## 典型坏味道

- **可变共享状态**：`static` 可变字段在多线程服务中引发竞态；改用无状态 Bean 或线程封闭（`ThreadLocal`）
- **过度继承**：多层 abstract class 继承链导致隐性耦合；优先组合（has-a）+ 接口，继承层级 ≤ 2
- **null 滥用**：方法返回 `null` 而非 `Optional`；调用方未做 null 检查；改用 `Optional` 或抛 `NoSuchElementException`
- **贫血模型**：领域对象仅有 getter/setter，业务逻辑堆在 Service 层；将行为移入实体
- **巨类/上帝类**：单个类承担多个职责，超过 300 行应检查是否需要拆分

## 安全陷阱

| 陷阱 | 后果 | 替代 |
|------|------|------|
| SQL 字符串拼接 | SQL 注入 | PreparedStatement 绑定参数 / ORM |
| `ObjectInputStream` 反序列化不可信数据 | RCE | 使用 JSON/Protobuf；或配置 `ObjectInputFilter` |
| XML 解析未禁用 DTD | XXE 攻击 | `factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true)` |
| 明文密码/密钥出现在代码或日志 | 凭证泄露 | 环境变量 + Vault；日志屏蔽敏感字段 |
| 不安全的随机数 `java.util.Random` | 可预测令牌 | `SecureRandom` 生成安全令牌 |
| 路径拼接用户输入 | 路径穿越 | `Path.normalize().startsWith(baseDir)` 验证 |

## 常见缺陷模式

- **NPE**：调用链未检查中间环节是否为 null；使用 `Objects.requireNonNull` 在入口显式防御
- **equals/hashCode 不一致**：覆写 `equals` 但未覆写 `hashCode`（或反向）；用 IDE 生成或 `record` 自动提供
- **资源泄漏**：`Connection` / `InputStream` / `PreparedStatement` 未在 try-with-resources 中关闭
- **空集合 vs null**：方法返回 `null` 而非空集合，调用方需额外 null 检查；返回 `Collections.emptyList()`
- **Integer 缓存陷阱**：`Integer a == Integer b` 在 -128~127 外返回 `false`；比较用 `equals()`

## 性能反模式

- **循环内字符串 `+` 拼接**：每次 `+` 创建新对象；改用 `StringBuilder` 或 `String.join`
- **自动装箱热路径**：`Integer` / `Long` 在循环中频繁装拆箱；改用原始类型或 `IntStream`
- **N+1 查询**：关联实体在循环内懒加载；用 `JOIN FETCH` / `EntityGraph` 批量加载
- **`ArrayList` 频繁头部插入**：O(n) 移位；改用 `LinkedList` 或 `ArrayDeque`（场景匹配时）
- **反复编译 `Pattern`**：在热路径内 `Pattern.compile(regex)`；提取为 `static final` 常量

## 评审 Checklist

1. 所有公共方法有 Javadoc 描述职责与参数约束（`@param` / `@throws`）
2. 无裸 `catch (Exception e) {}` 吞掉异常；至少记录日志或重抛
3. 外部输入未直接拼接 SQL / XML / 路径字符串
4. `AutoCloseable` 资源在 try-with-resources 中管理
5. `equals` 与 `hashCode` 同时覆写或同时不覆写
6. 集合方法返回空集合而非 null；Optional 链式处理无裸 `.get()`
7. 新增代码有对应单元测试，覆盖正常路径与异常路径
8. 并发访问的共享状态使用合适的同步原语或不可变对象
9. 异常信息未将 stacktrace / 内部细节直接返回给客户端响应
10. 引用的库与 API 真实存在，无虚构的方法或依赖坐标
