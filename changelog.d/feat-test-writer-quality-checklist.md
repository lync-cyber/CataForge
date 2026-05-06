### Added

- **test-writer §测试质量自检 checklist** —— 每个 `test()` / `it()` 块编写完成后强制三维度自检：(1) lint 白名单合规（4 类常见禁用规则替代 pattern：non-null assertion / `.not.toBeNull()` on `.find()` / `isNaN` / `delete obj.key`），(2) 测试名 ↔ 断言意图一致性（4 类反向 anti-pattern：反义 API 调用 / AC 语义 ↔ 断言 token 不符 / 测试数据 ↔ 名称反向 / Mock 缺失），(3) 跨平台 syscall 测试模式（决策树 + vi.hoisted + vi.mock(node:fs/promises) 模板代码 + fs.symlink/child.kill/chmod 三类典型场景）。配套 §Anti-Patterns 加一条"跨平台 syscall 优先 mock 而非 platform-skip"。
