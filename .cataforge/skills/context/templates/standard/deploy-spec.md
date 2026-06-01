---
id: "deploy-spec-{project}"
version: "{ver}"
doc_type: deploy-spec
author: devops
status: draft
deps: ["arch-{project}"]
consumers: [devops]
volume: main
required_sections:
  - "## 1. 构建流程"
  - "## 2. 环境配置"
  - "## 3. CI/CD流水线"
  - "## 4. 发布检查清单"
  - "## 5. 本地最小栈验证证据"
---
# Deployment Specification: {项目名称}

[NAV]
- §1 构建流程
- §2 环境配置
- §3 CI/CD流水线
- §4 发布检查清单
- §5 本地最小栈验证证据
[/NAV]

## 1. 构建流程
{构建命令/步骤}

## 2. 环境配置
| 环境 | 用途 | 配置差异 |
|------|------|----------|

## 3. CI/CD流水线
```yaml
stages:
  - lint
  - test
  - build
  - deploy
```

## 4. 发布检查清单
- [ ] 所有测试通过
- [ ] 版本号已更新
- [ ] CHANGELOG已更新
- [ ] 安全扫描通过

## 5. 本地最小栈验证证据
> 评审前人工启动最小本地栈并粘贴真实输出；本段为空或仅占位将被 doc-review 判 needs_revision。

- 启动命令: {项目最小本地栈的启动命令，例 `docker compose up -d db redis migrate api` 或等效}
- 验证项: {健康检查 / 关键端点联通 / migration 成功 / 进程存活}
- bring-up 日志摘录:
```
{粘贴真实启动日志关键行：依赖与服务就绪、监听端口、健康检查通过}
```
- 已核对的部署面: {构建入口 / 依赖声明 / 启动命令 / 服务调用方式 等实际验证到的项}
