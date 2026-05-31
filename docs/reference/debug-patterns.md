# 调试常见问题模式库 — 按语言/平台细则

> debug skill §同类扫描（scan-similar）引用的语言特定问题模式与扫描正则。skill 主体保持语言无关，本文档承载特定语言/平台的症状—修复对照。
>
> 新增语言/平台时在对应小节增条。

## Python / Windows

| 模式 | 特征 | 典型修复 |
|------|------|---------|
| Windows 编码 | `UnicodeEncodeError: 'charmap'` | stdout/stderr 包装 UTF-8 TextIOWrapper |
| 路径分隔符 | `FileNotFoundError` + 混用 `/` `\` | 使用 `os.path.join` 或 `pathlib` |
| 正则解析 | `re.error` 或匹配结果为 None | 转义特殊字符、检查 None 后再访问 `.group()` |
| JSON 编码 | `ensure_ascii=False` + 非 UTF-8 终端 | 输出前包装 stdout 编码 |
| 导入路径 | `ModuleNotFoundError` | 检查 `sys.path` 和相对/绝对导入 |

扫描特征示例（指令3 提取的 Grep 模式）：`print(.*ensure_ascii`、缺少 encoding 参数的 `open()`。
