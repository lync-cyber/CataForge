### Changed

- **deploy-spec 评审强制本地最小栈验证证据** —— deploy-spec 模板 `required_sections` 新增 `## 5. 本地最小栈验证证据`（启动命令 / 验证项 / bring-up 日志摘录 / 已核对部署面），doc-review Layer 1 `check_required_sections` 自动强制该段存在且非空；review Layer 2 加 deploy-spec 专属维度，核对证据为真实 bring-up 日志而非占位，否则 needs_revision。评审前被强制要求人工启动最小栈留证。
