### Added

- **Project Bootstrap 写入跨平台 `.gitattributes`** —— ORCHESTRATOR-PROTOCOLS §Project Bootstrap 新增 Step 3a：项目根目录无 `.gitattributes` 时写入最小集（`* text=auto eol=lf` + 常见文本/二进制扩展名），治理 Windows `core.autocrlf=true` 与 fixture/snapshot 字节哈希漂移导致的多平台测试 fail（reporter 在 wechat-typeset-X 0.1.1 实测 22 vitest snapshot fail 落地后清零）。已存在 `.gitattributes` 时只读判断（含 `eol=` 即视为已归一化），不动用户既有内容。闭环 [#103](https://github.com/lync-cyber/CataForge/issues/103) EXP-010。
