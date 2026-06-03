# Java · 构建部署细则

## 构建工具与打包

**Maven**：
```bash
mvn -B package -DskipTests          # CI 快速构建
mvn -B verify                        # 含集成测试
```
- Spring Boot 项目使用 `spring-boot-maven-plugin` 打可执行 fat-jar：`repackage` goal
- 非 Spring 项目用 `maven-shade-plugin`（合并依赖）或 `maven-assembly-plugin`

**Gradle**：
```bash
./gradlew build -x test              # 跳过测试
./gradlew shadowJar                  # 生成 shadow fat-jar
```

## 依赖锁定与可复现构建

- **Maven**：使用 `maven-dependency-plugin:resolve` + `dependency:list` 固化；或引入 **Takari Maven Wrapper** 锁定 Maven 版本；推荐 BOM（`<dependencyManagement>` + `import` scope）统一管理版本号，避免版本矩阵散落各 POM
- **Gradle**：`./gradlew dependencies --write-locks` 生成 `*.lockfile`；通过 `--dependency-verification=strict` 验证
- SNAPSHOT 依赖禁止出现在发布构建中；CI 可配 `enforcer:enforce` 检查
- 依赖坐标（groupId:artifactId:version）与基镜像 tag 须确认真实存在，不写臆造版本；改版本后重新解析并验证锁文件

## CI 缓存策略

**Maven（GitHub Actions 示例）**：
```yaml
- uses: actions/cache@v4
  with:
    path: ~/.m2/repository
    key: ${{ runner.os }}-maven-${{ hashFiles('**/pom.xml') }}
    restore-keys: ${{ runner.os }}-maven-
```

**Gradle**：
```yaml
- uses: actions/cache@v4
  with:
    path: |
      ~/.gradle/caches
      ~/.gradle/wrapper
    key: ${{ runner.os }}-gradle-${{ hashFiles('**/*.gradle*', '**/gradle-wrapper.properties') }}
```

Gradle Daemon 在 CI 中通常关闭（`--no-daemon`）避免进程残留。

## 容器基镜像

| 镜像 | 场景 | 说明 |
|------|------|------|
| `eclipse-temurin:21-jre-alpine` | 通用服务，轻量 | Alpine 基础，JRE only |
| `gcr.io/distroless/java21-debian12` | 安全敏感场景 | 无 shell，最小攻击面 |
| 自定义 `jlink` 镜像 | 裁剪模块，极致体积 | 需 module-info.java 配合 |

**分层构建（Dockerfile）**：
```dockerfile
FROM eclipse-temurin:21-jre-alpine AS runtime
WORKDIR /app
# Spring Boot 分层：依赖层在前，代码层在后，提升缓存命中
COPY --from=builder /app/target/extracted/dependencies ./
COPY --from=builder /app/target/extracted/spring-boot-loader ./
COPY --from=builder /app/target/extracted/snapshot-dependencies ./
COPY --from=builder /app/target/extracted/application ./
ENTRYPOINT ["java", "org.springframework.boot.loader.launch.JarLauncher"]
```

JVM 启动参数建议：`-XX:+UseContainerSupport`（容器感知 CPU/内存，Java 11+ 默认开启）；`-Xmx` 设置上限防止 OOM 被驱逐。

## 产物发布与版本管理

- 版本号遵循 SemVer；单一事实来源写在根 `pom.xml` 的 `<version>` 或 `gradle.properties`
- SNAPSHOT（`1.2.0-SNAPSHOT`）用于开发中间态，正式发布去掉 SNAPSHOT
- 内部制品库推荐 **Nexus** 或 **Artifactory**；开源库发布走 **Maven Central**（需 GPG 签名 + `nexus-staging-maven-plugin`）
- 发布后在 Git 打 tag：`git tag v1.2.0 && git push origin v1.2.0`
