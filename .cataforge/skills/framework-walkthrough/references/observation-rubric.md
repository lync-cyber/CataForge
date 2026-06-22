# 观察与归类口径

本文件定义走查过程中「看什么、怎么记、怎么归类」。走查的核心价值是过程信号，事后无法补采，故须逐阶段即时记录。

## 1. 逐阶段观察点

每跨一个阶段 / 门禁 / 降级 / 恢复，对照下列维度记录「期望 vs 实际」。维度对应 [`runtime-flow-map.md`](runtime-flow-map.md) 的路径 id，证据回填覆盖账本：

| 维度 | 对应路径 | 观察什么 | 异常信号示例 |
|------|---------|---------|------------|
| 初始化产物 | I-1~I-9 | Bootstrap 各步产物是否落地：目录集合/`.gitattributes`/{INSTRUCTION_FILE} 初版/框架版本/`runtime.platform`/env-block/permissions/kg init/context index | 版本仍 `0.0.0-template`、目录集合与模式不符、kg init 静默失败（注：`cataforge setup env-block` 在未配置技术栈时 exit 2 是预期占位行为，非缺陷） |
| 产物生成 | C-3, C-8 | 该阶段应产出的文档/代码是否生成、路径与命名是否合规；跨完阶段跑 `cataforge phase status` 作硬校验 | 文档缺 front matter、落错目录、未注册索引、`phase status` 退出非 0 |
| 门禁触发 | C-4, C-7, B-4 | doc-review / code-review / sprint-review 是否如期触发、Layer 1↔2 短路判定是否正确 | 该审却没审、该短路却全跑（反之亦然） |
| 一致性门 | C-5b~C-5f | Phase Transition 的 validate / reconcile / doc-consistency / claude-md check 是否逐步执行、阻塞类门是否真阻塞 | hygiene 越界却 WARN 放行、doc-consistency 在 Phase 2+ 未触发、EVENT BATCH 出现半截状态 |
| 降级行为 | B-8~B-11, E-9 | 缺能力 / 探针未装时降级是否显式、是否有日志 | 静默丢能力、未提示降级即继续、探针跳过被读作通过 |
| 恢复路径 | E-1~E-7 | 触发的恢复协议是否按 ORCHESTRATOR-PROTOCOLS 行为：轮次上限、人工介入触发、回滚是否干净 | 超轮次仍自动重试、rolled-back 静默、truncation 未评估完成度就接管 |
| CLI / skill / hook | C-*, E-8 | `cataforge` 子命令、`skill run`、hook 是否报错或退出码异常 | 命令不存在、参数不符、Layer 1 返回 2/127 |
| 文档加载 / KG | C-3, C-5c | `cataforge context read` 按 KG-active / legacy 分流是否正常；`graph` 模式下 authoring 落图 → `finalize` 导出 md → `reconcile` 归零的回环是否成立 | 实体级引用解析失败、drift 未被 reconcile 捕获、authoring 后 finalize 未重导出或 reconcile 残留 drift |
| 交互负担 | B-2, E-1 | 多少处需要人工代答、提问是否选择题优先、是否重复提问 | 同一问题反复问、开放式提问过多 |
| 状态一致 | T-2, T-3 | {INSTRUCTION_FILE} 项目状态 / EVENT-LOG 与实际推进是否一致 | 阶段标记与产物不符、事件漏写 |

**判定指引（易误判处）**：

- **KG 覆盖类 FAIL ≠ 自身漏写**：KG 覆盖 / 实体级交叉引用类 FAIL 多源于作者路径未把模块/功能/覆盖关系 ingest 进 KG，而非文档内容缺失（`context.mode = markdown` 无图后端，KG 被旁路，此类 FAIL 不出现）。归类前先确认是「KG 关系缺失」还是「文档真漏写」，前者归 `framework`/upstream，后者才是走查者漏填。
- **探针跳过（环境）≠ 真实通过**：`code-review scan` 等在裸环境因外部探针工具未装而跳过部分检查，仍可能报 `PASS / 0 findings`；须显式记录「N 个探针因工具未装跳过」，不可读作「代码无任何问题」。

## 2. 两类 findings

走查产出严格分两类，避免把「框架问题」与「走查方法问题」混为一谈：

- **framework**：被走查的框架本身的缺陷/摩擦——CLI/skill/hook 报错、门禁逻辑偏差、降级静默、文档契约不一致、跨平台行为差异等。这类 finding 反哺实现审查与跨平台评估。
- **process**：走查流程/本 skill 本身的可改进项——示例目标大小是否合适、步骤是否欠明确、观察口径是否漏项、沙盒搭建是否有坑、单轮预算是否合理等。这类 finding 反哺本 skill 的迭代。

## 3. 归类与严重度

每条 finding 套 COMMON-RULES：

- `category` 取自 §统一问题分类体系（completeness / consistency / convention / security / structure / error-handling / …）。
- `root_cause` 取自 §归因分类（self-caused / upstream-caused / input-caused / reviewer-calibration）。
- `severity`：CRITICAL（走查无法继续 / 数据被破坏）> HIGH（主干阶段功能性偏差）> MEDIUM（局部偏差有 workaround）> LOW（措辞/体验）。
- 证据：写明在哪个阶段、哪条命令、哪个产物路径上观察到，附原始输出片段或 `file:line`。

## 4. 报告结构

写 `docs/reviews/framework/FRAMEWORK-REVIEW-walkthrough-{YYYYMMDD}-r{N}.md`，首行 YAML front matter：

```yaml
---
id: "framework-review-walkthrough-{YYYYMMDD}-r{N}"
doc_type: framework-review
author: framework-walkthrough
status: draft
deps: []
---
```

正文建议章节：

1. **走查配置**：平台 / 执行模式 / 覆盖深度（smoke|full）/ 示例目标 / 框架版本。
2. **阶段时间线**：逐阶段「做了什么 → 产物 → 观察点」一行一条。
3. **路径覆盖账本**：[`runtime-flow-map.md`](runtime-flow-map.md) §2–§6 每条路径一行，字段按该文件 §7（path_id / disposition / result / evidence）。not-reached 必须写原因。这是覆盖面的自证——读者一眼看出哪条路径真跑了、哪条只是没触发。
4. **framework findings**：按 §问题格式 列出，severity 降序。
5. **process findings**：同上，聚焦本 skill 与走查方法。
6. **结论**：三态判定（COMMON-RULES §三态判定逻辑）+ 覆盖率（driven+probed / 全路径数）+ 最值得优先的改进项。

## 5. 自我校准

走查者须区分「框架真的有问题」与「走查者操作不当」。无法在沙盒复核、或源于走查者误用的现象，归 `process` 而非 `framework`，并在证据里写明判定依据，避免把操作失误冤枉成框架缺陷。
