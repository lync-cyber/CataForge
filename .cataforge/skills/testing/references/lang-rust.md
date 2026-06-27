# Rust · 测试编写细则

## 内置单元测试

- 单元测试与被测代码同文件，放在 `#[cfg(test)] mod tests { ... }` 块内。
- 每个测试函数加 `#[test]`；async 测试加 `#[tokio::test]`（tokio 项目）。
- 测试函数名描述预期行为，格式 `<单元>_<场景>_<预期结果>`，如 `parse_empty_input_returns_error`。

最小骨架：

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn add_positive_numbers_returns_sum() {
        assert_eq!(add(2, 3), 5);
    }

    #[test]
    fn divide_by_zero_returns_err() {
        assert!(divide(1, 0).is_err());
    }
}
```

## 断言宏选用

| 断言需求 | 宏 |
|---------|-----|
| 值相等 | `assert_eq!(actual, expected)` |
| 布尔条件 | `assert!(expr)` |
| 值不等 | `assert_ne!(a, b)` |
| 浮点近似 | `approx::assert_abs_diff_eq!`（`approx` crate）|
| 错误类型匹配 | `assert!(matches!(result, Err(MyError::NotFound)))` |

- `assert_eq!` 参数顺序惯例：左侧 actual，右侧 expected（panic 消息更易读）。

## 集成测试

- `tests/` 目录下每个 `.rs` 文件独立编译为一个集成测试二进制，仅能访问 `pub` API。
- 共用辅助函数放入 `tests/common/mod.rs`（或 `tests/helpers.rs`），避免在每个文件重复定义。
- 运行单个集成测试文件：`cargo test --test <文件名>`。

## 参数化测试（rstest）

```rust
use rstest::rstest;

#[rstest]
#[case(1, 1, 2)]
#[case(0, 5, 5)]
#[case(-1, 1, 0)]
fn add_cases(#[case] a: i32, #[case] b: i32, #[case] expected: i32) {
    assert_eq!(add(a, b), expected);
}
```

- `rstest` 同时支持 fixtures（`#[fixture]`）实现测试间共享初始化逻辑。

## Mock（trait + mockall）

- 被测逻辑依赖外部服务时，先定义 trait 抽象（如 `trait UserRepository`），再用 `mockall::automock` 生成 mock：

```rust
#[cfg_attr(test, mockall::automock)]
pub trait UserRepository {
    fn find_by_id(&self, id: u64) -> Option<User>;
}

// 测试中
let mut mock = MockUserRepository::new();
mock.expect_find_by_id().returning(|_| Some(User::default()));
```

- mock 仅在 `#[cfg(test)]` 下生成，不污染生产代码。

## 文档测试

- 公开函数的 `///` 注释中的代码块默认由 `cargo test --doc` 执行。
- 文档示例应覆盖最常见用法；`# let x = setup();` 前缀 `#` 可隐藏样板行。

## 覆盖率

- 推荐 `cargo-llvm-cov`：`cargo llvm-cov --html` 生成 HTML 报告；CI 可加 `--lcov` 输出供覆盖率平台消费。
- 备选：`cargo-tarpaulin`（仅 Linux），适合不依赖 LLVM 工具链的环境。
- 覆盖率目标因项目性质而定；关键业务逻辑 / 错误路径应有显式测试，不以数字指标代替判断。
- 断言须能真正失败，避免只 `assert!(result.is_ok())` 的空壳；补错误变体（`matches!(.., Err(..))`）与边界，不要只测正常输入
