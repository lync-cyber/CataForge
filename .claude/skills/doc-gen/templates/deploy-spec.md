# Deployment Specification: {项目名称}
<!-- id: deploy-spec-{project}-{ver} | author: devops | status: draft -->
<!-- deps: arch-{project}-{ver} | consumers: devops -->
<!-- volume: main -->

[NAV]
- §1 构建流程
- §2 环境配置
- §3 CI/CD流水线
- §4 发布检查清单
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