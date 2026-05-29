---
id: "research-feedback-doc-drift"
doc_type: research-note
author: reviewer
status: draft
deps: []
consumers: [orchestrator, architect, tech-lead]
---

# 用户反馈分析：文档漂移、引用腐化与迭代规划

## 研究方法

对 CataForge v0.4.0 全量源码与 Skill/Agent/Protocol 定义进行审查，覆盖：
- orchestrator 阶段调度与 Phase Transition Protocol
- doc-gen / doc-review / doc-nav / task-decomp / task-dep-analysis 五个核心 Skill
- COMMON-RULES / ORCHESTRATOR-PROTOCOLS / SUB-AGENT-PROTOCOLS
- `src/cataforge/domain/docs/indexer.py` / `loader.py` / `checker.py`
- `framework.json` 常量与 feature 配置
- 文档模板 `_registry.yaml` 及 standard/volumes/lite 模板

---

## 反馈一：跨多轮会话大项目中 PRD/ARCH/PLAN 漂移导致最终代码严重偏移

### 结论：属实。是框架当前最严重的结构性缺陷。

### 问题定位

#### 根因 1：缺乏版本化依赖追踪

当前 `deps` 字段仅记录文档 ID，不含版本约束：

```yaml
# 当前实现 (indexer.py line 138)
deps: ["prd-myproject"]           # 无版本信息
```

当 PRD 从 v1.0 修订到 v1.1（新增 F-004、修改 F-002 的验收标准），ARCH 仍然声明 `deps: ["prd-myproject"]`，indexer 认为引用合法——它只验证**目标存在**，不验证**内容一致**。这意味着：

- ARCH 可能遗漏 F-004 的模块映射
- DEV-PLAN 的任务卡可能基于 F-002 的旧版验收标准
- 最终代码实现的是过时需求

#### 根因 2：缺乏双向覆盖验证

doc-review Layer 2 的 `consistency` 维度只检查"ARCH 引用的 F-NNN 是否在 PRD 中存在"（正向），不检查"PRD 中的 F-NNN 是否全部被 ARCH 覆盖"（反向）。这导致：

- PRD 有 10 个功能，ARCH 只映射了 7 个——doc-review 不会发现
- DEV-PLAN 从 ARCH 产出任务，缺失的 3 个功能永远不会进入开发
- 最终交付缺少 30% 的功能

#### 根因 3：无级联失效传播机制

Phase Transition Protocol 只检查"当前文档是否 approved"，不检查"当前文档的上游是否在其 approved 之后发生过变更"。

典型漂移场景：
```
Session 1: PRD v1.0 approved → ARCH approved → DEV-PLAN approved
Session 2: 用户要求修改 PRD（新增功能）→ PRD v1.1 approved
           但 ARCH 仍基于 v1.0，DEV-PLAN 仍基于旧 ARCH
Session 3: 开发按 DEV-PLAN 实施，最终产品与 PRD v1.1 不匹配
```

Change Request Protocol 的 `cascade_amendment` 可以级联更新，但它只在**用户主动发起变更请求**时触发。如果用户在 Session 2 中通过 Revision Protocol（reviewer 发起）修改 PRD，级联不会自动触发。

#### 根因 4：跨会话状态仅靠 CLAUDE.md 文本

CLAUDE.md 记录"文档状态: approved"，但不记录 approved 时的内容快照或哈希。新会话恢复时，orchestrator 只能看到状态标签，无法判断文档内容是否在上次 approved 后被修改过。

### 改进建议

#### 建议 1.1：引入版本化依赖追踪（高优先级）

在 `deps` 字段中追加版本约束，indexer 增加版本比对逻辑：

```yaml
# 改进后的 deps 格式
deps:
  - ref: "prd-myproject"
    pinned_version: "1.0.0"
    pinned_hash: "a3f8c2"      # 文档内容的短哈希
```

实现要点：
- `indexer.py` 的 `build_index()` 为每个文档计算内容哈希（取 YAML front matter 之后的 body 部分，`hashlib.sha256(body.encode()).hexdigest()[:8]`）
- `find_xref_errors()` 增加 `find_stale_deps()` 子检查：比对 `pinned_version` / `pinned_hash` 与当前索引中上游文档的实际值
- `cataforge docs validate` 输出 `[STALE-DEP]` 级别警告
- doc-gen `finalize` 步骤自动填充 `pinned_version` 和 `pinned_hash`

#### 建议 1.2：实现双向覆盖矩阵（高优先级）

在 doc-review Layer 1 增加覆盖矩阵检查：

```python
# checker.py 新增检查
def check_bidirectional_coverage(self):
    """验证下游文档是否完整覆盖上游文档的所有 item。"""
    coverage_map = {
        "arch":     {"upstream": "prd",  "upstream_prefix": "F",  "downstream_prefix": "M"},
        "dev-plan": {"upstream": "arch", "upstream_prefix": "M",  "downstream_prefix": "T"},
        "ui-spec":  {"upstream": "prd",  "upstream_prefix": "F",  "downstream_prefix": ["C", "P"]},
    }
    # 从上游文档提取所有 item ID
    # 在当前文档正文中搜索对上游 item 的引用
    # 未被引用的上游 item → CRITICAL: "F-004 未在 ARCH 中映射到任何模块"
```

同时在 doc-review Layer 2 的 `completeness` 维度增加明确指令：逐一核对上游文档的 item 列表，确认当前文档是否遗漏。

#### 建议 1.3：上游变更时自动标记下游过期（高优先级）

在 Phase Transition Protocol 中增加依赖新鲜度检查：

```
Phase Transition Protocol — 新增 Step 1.5:
1.5 **依赖新鲜度检查** — 遍历 .doc-index.json，对当前阶段及所有下游文档：
    - 读取 deps[].pinned_hash
    - 比对上游文档当前哈希
    - 不匹配 → 该文档标记为 stale_deps，向用户展示:
      "ARCH (v1.0, hash=a3f8c2) 依赖 PRD (pinned_hash=a3f8c2)，但 PRD 当前 hash=b7d4e1。
       ARCH 可能需要更新以反映 PRD 的变更。"
    - 用户可选择：(1) 进入 cascade_amendment (2) 确认变更不影响、继续
```

#### 建议 1.4：跨会话恢复时的一致性校验（中优先级）

在 Startup Protocol（会话恢复）中增加：

```
Session Resume — 新增步骤:
- 运行 cataforge docs validate --check-staleness
- 若存在 stale deps，在用户首次交互前展示警告
- 若存在 orphan docs 或 broken xrefs，也一并展示
```

#### 建议 1.5：引入需求追踪矩阵文档（中优先级）

在 doc-gen 增加 `traceability-matrix` 模板，自动生成追踪矩阵：

```markdown
# 需求追踪矩阵

| PRD Feature | ARCH Module | ARCH API | DEV-PLAN Task | UI-SPEC Component | Status |
|---|---|---|---|---|---|
| F-001 | M-001 | API-001 | T-001, T-002 | C-001, P-001 | covered |
| F-002 | M-002 | API-002 | T-003 | — | covered |
| F-003 | — | — | — | — | **UNCOVERED** |
```

该矩阵从 `.doc-index.json` 的 xref map 自动生成，作为 Phase Transition 的辅助决策信息。

---

## 反馈二：文档修订时编号和引用需手动更新，LLM 幻觉/遗漏导致文档腐化；知识图谱式元数据能否实现自动更新？

### 结论：属实。当前框架对引用一致性的保障是"检测后修复"而非"修改时自动维护"。

### 问题定位

#### 根因 1：编号系统是纯文本约定，无机器强制

Item ID（F-001, M-001, T-001）是 markdown heading 中的文本标记：

```markdown
### F-001: 用户登录
### F-002: 权限管理
### F-003: 数据导出
```

当需要在 F-001 和 F-002 之间插入新功能时，LLM 面临两个选择：
- 插入 F-001a（违反 `ITEM_ID_RE = ^[A-Z]+-\d+$`）
- 重新编号为 F-001, F-002(新), F-003(原F-002), F-004(原F-003)

后者需要同时更新所有引用 F-002、F-003 的下游文档——这正是 LLM 最容易遗漏的操作。

#### 根因 2：交叉引用是字符串匹配，无反向索引

`build_xref()` 构建了 item→location 的正向映射，但没有 item→referrers 的反向映射。当 F-002 被重编号为 F-003 时，系统无法知道哪些文档的 `deps` 或正文中引用了 F-002，也就无法自动更新这些引用。

#### 根因 3：`checker.py` 的引用验证粒度不够

`check_xref()` 使用宽松正则 `([\w-]+)#([\w§.\-]+)` 提取引用后，只用文件名 glob 验证目标文档是否存在，不验证 section/item 是否存在。而 `find_xref_errors()` 在 indexer 中做了更严格的验证，但只在 `cataforge docs validate` 时运行，不在文档修订的实时流程中触发。

#### 根因 4：文档正文中的非结构化引用不被追踪

文档正文中的散文引用（如"参见 ARCH 中的用户认证模块 M-001"）不在 front matter `deps` 中，indexer 不追踪。这类引用在重编号后会静默失效。

### 知识图谱式元数据的可行性分析

#### 核心思路

将文档间的关系从"嵌入文本的字符串引用"提升为"结构化的图数据"：

```
节点: 每个 Item ID 是一个节点（F-001, M-001, T-001, API-001, etc.）
边:   implements(M-001, F-001)       # ARCH 模块实现 PRD 功能
      decomposes(T-001, M-001)       # 任务分解自模块
      depends_on(T-002, T-001)       # 任务依赖
      validates(AC-001, F-001)       # 验收标准验证功能
      renders(C-001, F-001)          # UI 组件渲染功能
```

#### 可行方案：基于 `.doc-index.json` 扩展的轻量图

不需要引入 Neo4j 等外部图数据库。在现有 `.doc-index.json` 的 `xref` map 基础上扩展：

```json
{
  "xref": {
    "F-001": [
      {"doc_id": "prd-foo", "section": "2", "file_path": "docs/prd/prd-foo.md"}
    ]
  },
  "graph": {
    "nodes": {
      "F-001": {"type": "feature", "doc_id": "prd-foo", "label": "用户登录", "hash": "a3f8c2"},
      "M-001": {"type": "module",  "doc_id": "arch-foo", "label": "认证模块", "hash": "b7d4e1"},
      "T-001": {"type": "task",    "doc_id": "dev-plan-foo", "label": "登录 API", "hash": "c9e5f3"}
    },
    "edges": [
      {"from": "M-001", "to": "F-001", "rel": "implements"},
      {"from": "T-001", "to": "M-001", "rel": "decomposes"},
      {"from": "T-001", "to": "F-001", "rel": "traces_to"}
    ],
    "reverse_index": {
      "F-001": {
        "implemented_by": ["M-001"],
        "decomposed_to": ["T-001", "T-002"],
        "validated_by": ["AC-001", "AC-002"],
        "rendered_by": ["C-001"]
      }
    }
  }
}
```

#### 自动更新机制

有了图结构，以下场景可以自动处理：

**场景 A：Item 重编号**
```
用户操作: F-002 重编号为 F-003
系统响应:
1. 从 reverse_index["F-002"] 获取所有引用者: [M-002, T-003, AC-003]
2. 在 M-002 所在文档中，sed "F-002" → "F-003"
3. 在 T-003 所在文档中，sed "F-002" → "F-003"
4. 更新 graph.nodes 和 edges
5. 重建 reverse_index
6. 输出变更清单供用户确认
```

**场景 B：Item 删除**
```
用户操作: 删除 F-003
系统响应:
1. 从 reverse_index["F-003"] 获取引用者: [M-003, T-005]
2. 标记 M-003 和 T-005 为 orphaned（依赖已删除的上游 item）
3. 向用户展示影响范围，要求决策：
   - 级联删除 M-003 和 T-005
   - 将 M-003 重新映射到其他 Feature
   - 保留但标记 [ORPHANED] 待后续处理
```

**场景 C：Item 新增**
```
用户操作: 在 PRD 中新增 F-004
系统响应:
1. graph.nodes 新增 F-004
2. reverse_index["F-004"] = {implemented_by: [], decomposed_to: [], ...}
3. 覆盖矩阵自动标记 F-004 为 UNCOVERED
4. Phase Transition 时展示: "F-004 尚未映射到任何 ARCH 模块"
```

#### 实现路径建议

1. **阶段一（最小可行）**：在 `indexer.py` 的 `build_xref()` 基础上增加 `build_graph()` 函数，解析文档正文中的 item 引用关系（基于 `context_load` 字段和正文中的 `#§N.Item` 引用），生成 `graph` 和 `reverse_index` 字段到 `.doc-index.json`

2. **阶段二（自动传播）**：在 doc-gen 的 `write-section` 步骤中，当检测到 item ID 变更（通过 git diff 解析），自动调用 `reverse_index` 查找受影响文档，生成变更建议（但不自动修改，由用户确认）

3. **阶段三（完全自动化）**：引入 `cataforge docs rename-item F-002 F-003` 命令，自动完成图更新 + 文档正文更新 + 索引重建。引入 `cataforge docs insert-item --after F-001 --doc prd-myproject` 命令，自动重编号并传播

#### 与纯 LLM 方案的对比

| 维度 | 纯 LLM（当前） | 图元数据（建议） |
|---|---|---|
| 引用更新 | 依赖 LLM 记忆和注意力，会遗漏 | 反向索引驱动，零遗漏 |
| 编号重排 | LLM 需扫描全部文档，token 消耗大 | 图查询 O(1)，精确定位 |
| 覆盖检测 | doc-review Layer 2 隐含检查 | 图遍历自动检测 |
| 一致性保障 | 事后检测（validate 时才发现） | 修改时即时传播 |
| 跨会话可靠性 | 依赖 CLAUDE.md 文本描述 | `.doc-index.json` 持久化 |

### 其他改进建议

#### 建议 2.1：引入稳定 UUID 作为 Item 内部标识（高优先级）

显示编号 F-001 可能因插入/删除而变动，但内部使用稳定的 UUID 作为引用锚点：

```markdown
### F-001: 用户登录 <!-- item-uuid: feat-auth-login -->
```

跨文档引用使用 UUID 而非编号：`prd#feat-auth-login`。编号仅用于人类阅读，UUID 用于机器引用。编号变动时改写 heading 文本即可，引用层（其他文档中的 `prd#feat-auth-login`）不动。

#### 建议 2.2：doc-gen 修订模式增加引用完整性保障（高优先级）

在 doc-gen SKILL.md 中增加 `revise` 步骤定义：

```
Step: revise
1. 对比修订前后的 item 列表变化（新增/删除/重编号）
2. 调用 cataforge docs reverse-deps {changed_items} 获取受影响文档
3. 生成引用更新指令清单
4. 依次更新受影响文档的引用
5. 运行 cataforge docs validate 确认无断裂引用
```

#### 建议 2.3：实时引用验证 hook（中优先级）

在 doc-gen `write-section` 完成后、`finalize` 之前，增加引用验证 hook：

```bash
# PostToolUse hook for Write/Edit on docs/**/*.md
cataforge docs validate --quick --file ${file_path}
```

这将在每次文档编辑后即时检查引用完整性，而不是等到 `finalize` 或手动 `validate` 时才发现。

---

## 反馈三：大型项目应合理规划功能迭代，在关键节点引入用户手动功能检查以避免偏移返工

### 结论：属实。当前框架的用户检查点设计过于稀疏，不适合大型项目的渐进式交付。

### 问题定位

#### 根因 1：默认检查点只有两个，且位于流程首尾

`MANUAL_REVIEW_CHECKPOINTS` 默认值为 `["pre_dev", "pre_deploy"]`：
- `pre_dev`：Phase 4→5 转换时（所有文档已写完，即将开始编码）
- `pre_deploy`：Phase 6→7 转换时（所有代码已写完，即将部署）

这意味着在整个开发阶段（Phase 5），用户没有任何强制检查点。如果项目有 20 个任务分 5 个 Sprint，用户要等全部 Sprint 完成后才能看到产出并验证是否符合预期。

#### 根因 2：`post_sprint` 检查点存在但默认关闭

framework.json 的 `MANUAL_REVIEW_CHECKPOINTS` 不含 `post_sprint`。ORCHESTRATOR-PROTOCOLS 中定义了 `post_sprint` 选项（Sprint Review approved 后、进入下一 Sprint 前命中），但用户需要在 Bootstrap 时或 CLAUDE.md 中手动添加。大多数用户不知道这个选项存在。

#### 根因 3：Sprint Review 是自动化审查，不含用户功能验证

Sprint Review 由 reviewer agent 执行，检查交付物完整性、AC 覆盖率、代码质量等——但这些都是**代码层面**的检查。对于"用户用浏览器操作功能、确认行为符合预期"这类**功能层面**的验证，框架完全没有机制。

`PRE_DEPLOY_DEMO_REQUIRED` 只在 pre_deploy 检查点生效（整个开发完成后）。即使启用，也是"一次性终验"而非"渐进式确认"。

#### 根因 4：任务规划缺乏 MVP 切分意识

task-decomp 按模块和依赖关系分 Sprint，但不考虑"用户价值交付单元"。一个 Sprint 可能包含 3 个后端 API 任务但没有前端页面——用户在这个 Sprint 后无法体验任何完整功能。

### 改进建议

#### 建议 3.1：将 `post_sprint` 作为 standard 模式的默认检查点（高优先级）

修改 `framework.json`：

```json
"MANUAL_REVIEW_CHECKPOINTS": ["pre_dev", "post_sprint", "pre_deploy"]
```

`post_sprint` 检查点的交互设计：

```
=== Sprint N 完成确认 ===
已完成任务: T-001 (用户登录 API), T-002 (JWT 认证), T-003 (登录页面)
通过率: 3/3 (100%)
新增功能: 用户可通过登录页面完成注册和登录

选项:
1. 确认继续下一 Sprint
2. 暂停，我需要手动验证功能
3. 发现偏移，需要调整需求（进入 Change Request）
4. 已在浏览器验证核心功能正常工作 ← (user_facing Sprint 时出现)
```

#### 建议 3.2：引入"功能验证任务"类型（高优先级）

在 task-decomp 中增加 `task_kind: validation` 类型：

```markdown
### T-010: [VALIDATION] 用户登录流程端到端验证
- **目标**: 用户手动验证登录功能的完整流程
- **task_kind**: validation
- **验证清单**:
  - [ ] 打开登录页面，确认 UI 布局正确
  - [ ] 输入有效凭据，确认登录成功并跳转
  - [ ] 输入无效凭据，确认错误提示正确
  - [ ] 退出登录，确认会话清除
- **前置任务**: [T-001, T-002, T-003]
- **执行者**: 用户（非 Agent）
```

validation 任务的特征：
- 不进入 TDD 流程，不产出代码
- orchestrator 遇到 validation 任务时暂停并使用 AskUserQuestion 展示验证清单
- 用户完成验证后选择"通过"/"不通过"/"发现问题"
- "不通过" → 进入 Revision Protocol 或 Change Request

#### 建议 3.3：task-decomp 增加 MVP 切分策略（高优先级）

在 task-decomp SKILL.md 中增加 Sprint 划分原则：

```
Sprint 划分的 MVP 原则:
1. 每个 Sprint 的产出必须包含至少一个用户可感知的完整功能
   — 后端 API + 前端页面 + 路由集成 = 一个可验证的功能单元
2. 优先安排用户核心路径（user_facing_critical_path=true）的任务到前几个 Sprint
3. 每个包含 user_facing 任务的 Sprint 末尾自动插入 validation 任务
4. 基础设施任务（数据库、认证、CI/CD）集中在 Sprint 1
   — Sprint 1 例外：不要求用户可感知功能，但要求所有后续 Sprint 的前置条件就绪
```

#### 建议 3.4：引入里程碑（Milestone）概念（中优先级）

在 DEV-PLAN 模板中增加 Milestone 定义层：

```markdown
## 4. 里程碑计划

### Milestone 1: 核心功能可用 (Sprint 1-2)
- **交付功能**: 用户注册、登录、基础数据展示
- **验收标准**: 用户可完成注册→登录→查看数据的完整流程
- **验证方式**: 用户手动验证 + 截图确认
- **Go/No-Go 决策点**: 是否继续开发高级功能

### Milestone 2: 完整功能 (Sprint 3-4)
- **交付功能**: 数据编辑、导出、权限管理
- **验收标准**: 所有 PRD 功能可用
- **验证方式**: 用户手动验证 + 自动化回归测试
```

Milestone 与 `MANUAL_REVIEW_CHECKPOINTS` 集成：每个 Milestone 结束时触发增强版 `post_sprint` 检查点，包含功能演示要求。

#### 建议 3.5：Sprint 级偏移检测（中优先级）

在 sprint-review skill 中增加偏移检测维度：

```
Sprint 偏移检测:
1. 对比本 Sprint 实际交付的 AC 与 DEV-PLAN 中规划的 AC
   - 未交付的 AC → 延期风险信号
   - 计划外的 AC → 范围蔓延信号
2. 对比本 Sprint 实际代码文件路径与 DEV-PLAN deliverables 声明
   - 计划外文件 > 30% → gold-plating 警告
3. 累计偏移率 = (延期 AC + 计划外 AC) / 总 AC
   - 偏移率 > 20% → 向用户展示偏移警告并建议重新评估剩余 Sprint
```

---

## 综合改进优先级排序

| 优先级 | 建议 | 预期影响 | 实现复杂度 |
|---|---|---|---|
| P0 | 1.2 双向覆盖矩阵 | 消除功能遗漏 | 中 |
| P0 | 1.1 版本化依赖追踪 | 消除静默漂移 | 中 |
| P0 | 3.1 post_sprint 默认启用 | 渐进式验证 | 低 |
| P0 | 3.2 validation 任务类型 | 用户主动验证 | 中 |
| P1 | 1.3 上游变更自动标记下游过期 | 主动漂移预警 | 中 |
| P1 | 2.1 稳定 UUID 内部标识 | 消除重编号连锁反应 | 高 |
| P1 | 3.3 MVP 切分策略 | 有意义的增量交付 | 低 |
| P1 | 2.x 图元数据（阶段一） | 反向引用追踪 | 中 |
| P2 | 1.4 跨会话恢复校验 | 恢复时发现问题 | 低 |
| P2 | 1.5 需求追踪矩阵文档 | 可视化覆盖状态 | 低 |
| P2 | 2.2 doc-gen revise 模式 | 修订时自动维护引用 | 中 |
| P2 | 2.3 实时引用验证 hook | 编辑时即时反馈 | 低 |
| P2 | 3.4 里程碑概念 | 阶段性交付目标 | 低 |
| P2 | 3.5 Sprint 级偏移检测 | 量化偏移趋势 | 中 |

---

## 结论

三个反馈问题均属实，且互相关联：

1. **文档漂移**的根因是缺乏版本化依赖追踪和双向覆盖验证——框架能检测"引用目标是否存在"，但不能检测"引用目标是否仍然是写引用时的版本"，也不能检测"上游的所有 item 是否都被下游覆盖"。

2. **引用腐化**的根因是引用系统缺乏反向索引——当 item 变更时，系统不知道谁引用了它。知识图谱式的元数据可以解决这个问题，且不需要外部数据库，在现有 `.doc-index.json` 基础上扩展 `graph` 和 `reverse_index` 字段即可实现。

3. **缺乏迭代检查点**的根因是框架设计倾向于"自动化优先"——Sprint Review 由 AI 完成，用户只在 Phase 边界参与。对大型项目，这导致长时间无人工干预的"盲飞"。需要将 `post_sprint` 设为默认检查点，并引入 validation 任务类型和 MVP 切分策略。

这三个问题形成恶性循环：文档漂移导致任务偏移 → 缺乏中间检查点使偏移持续积累 → 最终产出与需求严重不匹配 → 引用腐化使修复成本倍增。改进需要同时从三个维度入手，其中 P0 级别的四项建议（双向覆盖矩阵、版本化依赖追踪、post_sprint 默认启用、validation 任务类型）构成最小可行改进集。
