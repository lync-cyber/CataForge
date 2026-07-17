# ## Fixed

- **testing skill 调用示例与 CLI 解析对齐** —— SKILL.md / qa-engineer AGENT.md 的
  `cataforge skill run testing -- scan-e2e tests/e2e/` 示例改为 `-- tests/e2e/`：skill runner
  无子命令概念，`--` 后全部 token 直传脚本 positional，`scan-e2e` 会被当作目标路径导致 exit 2。
