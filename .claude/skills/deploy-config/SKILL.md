---
name: deploy-config
description: "部署配置 — CI/CD流水线、容器化、环境配置、基础设施即代码。"
argument-hint: "<操作: pipeline|container|env|iac> <平台或环境类型>"
suggested-tools: Read, Write, Edit, Bash
depends: [doc-gen, doc-nav]
disable-model-invocation: false
user-invocable: true
---

# 部署配置 (deploy-config)

## 能力边界
- 能做: CI/CD流水线配置、构建脚本编写、自动化测试集成、部署配置、容器化配置(Dockerfile/docker-compose)、环境配置管理、基础设施即代码(IaC)
- 不做: 源代码修改、测试编写、架构变更

## 输入规范
- arch#§1.4技术栈
- arch#§6目录结构
- test-report测试配置(流水线阶段)
- deploy-spec环境配置(容器/IaC阶段)

## 输出规范
- CI/CD配置文件(如 .github/workflows/)
- 构建脚本
- 容器化文件(Dockerfile, docker-compose.yml)
- 环境配置文件(.env.dev/.env.staging/.env.prod)
- IaC配置(Terraform/K8s manifests, 如适用)

## 操作指令

### 指令1: CI/CD流水线 (pipeline)

#### Step 1: 平台选型
根据arch#§1.4技术栈决定CI/CD平台:
- **GitHub Actions**(默认): 项目托管在GitHub时
- **GitLab CI**: 项目托管在GitLab时
- **Jenkins**: 企业内部部署、复杂流水线需求时
- 不确定时通过doc-nav查阅arch#§1.4技术栈决策，信息不足则标注[ASSUMPTION]

#### Step 2: 配置标准流水线阶段
按以下顺序配置流水线:
```
lint → unit-test → integration-test → build → deploy-staging → e2e-test → deploy-prod
```
- 每个阶段定义明确的成功/失败条件
- 阶段间设置依赖(前序失败则阻断后续)
- PR触发: lint + unit-test + integration-test
- 主分支合并: 完整流水线

#### Step 3: 集成自动化测试
- 单元测试: 每次push触发
- 集成测试: PR和主分支触发
- E2E测试: 部署到staging后触发
- 覆盖率报告: 集成到PR检查中

#### Step 4: 环境变量与密钥管理
- secrets通过平台机制注入:
  - GitHub: Repository Secrets / Environment Secrets
  - GitLab: CI/CD Variables (masked + protected)
  - Jenkins: Credentials Store
- 禁止硬编码任何密钥或敏感信息
- 环境差异通过环境变量控制(dev/staging/prod)

#### Step 5: 缓存策略
- 依赖缓存: node_modules / pip cache / maven .m2 等
- 构建缓存: Docker layer cache / 编译产物缓存
- 缓存key包含lock文件hash，确保依赖变更时刷新

#### Step 6: 发布检查清单
- 版本号: package.json/pyproject.toml 与 Git tag 一致
- changelog: 已更新且包含当前版本条目
- 构建产物: 存档到artifact存储
- 通知: 部署结果通知(Slack/邮件/webhook)

### 指令2: 容器化配置 (container)

#### Step 1: Dockerfile编写
遵循最佳实践:
- **多阶段构建**: 分离构建环境和运行环境，减小镜像体积
- **最小基础镜像**: 优先使用alpine/slim/distroless变体
- **非root用户**: 创建专用用户运行应用
- **.dockerignore**: 排除node_modules、.git、测试文件等
- **层缓存优化**: 依赖安装层在代码复制层之前
- **健康检查**: 定义HEALTHCHECK指令

#### Step 2: docker-compose编排
- **服务定义**: 每个服务指定image/build、ports、volumes、depends_on
- **网络**: 定义服务间通信网络(前端/后端/数据库分离)
- **卷**: 数据持久化卷(数据库) + 开发时代码热重载卷
- **健康检查**: 依赖服务设置healthcheck，使用depends_on.condition: service_healthy
- **compose profiles**: 通过profiles区分dev/test/prod服务组合

### 指令3: 环境配置 (env)

#### Step 1: 基础设施需求分析
根据arch#§1.4技术栈确定:
- 运行时环境(Node.js / Python / Go / JVM等)
- 依赖服务(数据库、缓存、消息队列等)
- 部署目标: 单机(docker-compose) / 云(Terraform) / 集群(K8s manifests)

#### Step 2: 环境差异管理
- 通过env文件区分环境: `.env.dev` / `.env.staging` / `.env.prod`
- 敏感配置不入仓库(通过.gitignore排除)
- 环境变量分层:
  - 通用配置: docker-compose.yml中定义
  - 环境特定: env文件覆盖
  - 密钥: 通过平台secret机制注入

### 指令4: IaC配置 (iac)
根据部署目标选择:
- **docker-compose**: 单机部署，适合小型项目
- **Terraform**: 云资源编排(AWS/GCP/Azure)，state远程存储
- **K8s manifests/Helm**: 集群部署，支持水平扩展和自动恢复
- 配置版本化，纳入代码仓库

## 密钥管理规范
所有部署配置必须遵循以下密钥管理要求:

### 禁止事项
- 禁止将密钥、Token、密码硬编码到配置文件或代码中
- 禁止将 `.env` 文件（含敏感值）提交到版本控制
- 禁止在 CI/CD 日志中输出密钥值（注意 `--verbose` 模式可能泄露）

### 密钥注入策略（按优先级）
1. **平台原生 Secret 机制**（推荐）:
   - GitHub Actions: `${{ secrets.MY_SECRET }}`，通过 Repository/Environment Secrets 配置
   - GitLab CI: `$MY_SECRET`，通过 CI/CD Variables (masked + protected) 配置
   - Jenkins: `withCredentials([string(credentialsId: 'my-secret', variable: 'MY_SECRET')])`
2. **外部 Secret Manager**（生产环境推荐）:
   - AWS Secrets Manager / Azure Key Vault / GCP Secret Manager / HashiCorp Vault
   - 应用启动时动态拉取，不持久化到文件系统
3. **环境变量文件**（仅限本地开发）:
   - `.env.dev` 仅含开发用非敏感配置（如 `API_URL=http://localhost:3000`）
   - `.env.example` 作为模板提交到仓库（仅含键名，不含实际值）
   - `.env*`（含敏感值的）必须在 `.gitignore` 中排除

### 密钥清单模板
deploy-spec 文档中必须包含密钥清单节:
```
| 密钥名 | 用途 | 注入方式 | 环境 | 轮换策略 |
|--------|------|---------|------|---------|
| DB_PASSWORD | 数据库连接 | GitHub Secret | all | 90天 |
| API_KEY | 第三方API | Secret Manager | prod | 按需 |
```

## 效率策略
- 配置文件模板化，按项目技术栈适配
- 密钥通过环境变量注入，不硬编码
- Dockerfile层顺序优化，最大化构建缓存命中
- 环境差异最小化，通过变量控制
- 利用缓存减少重复构建时间
