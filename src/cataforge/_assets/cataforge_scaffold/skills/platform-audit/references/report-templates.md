# 审计报告模板

`Phase 2 / Step 6` 的差异报告 + `Phase 4 / Step 15` 的总结模板。

---

## 差异报告 (Step 6)

```
# 平台审计差异报告
生成时间: <date>
审计范围: <platforms>

## 变更摘要
| 平台 | CRITICAL | MAJOR | MINOR | INFO |
|------|----------|-------|-------|------|

## 详细差异

### <platform_id> (v<old> → v<new>)

#### CRITICAL
- [tool_map] file_edit: StrReplace → Write (Cursor v3.x 合并了编辑工具)
  影响: profile.yaml, test_platform.py, test_translator.py, test_hook_bridge.py

#### MAJOR
- [features] agent_teams: false → true (Claude Code 新增 Agent Teams)
  影响: profile.yaml
- [agent_config] 新增字段: effort, color, isolation
  影响: profile.yaml
- [hooks.degradation] guard_dangerous: degraded → native (Codex 已支持 hooks.json)
  影响: profile.yaml, hook bridge 生成
```

---

## 审计完成总结 (Step 15)

```
# 审计完成总结
日期: <date>
平台: <list>

## 更新统计
| 类型 | 文件数 | 变更项 |
|------|--------|--------|
| profile.yaml | N | ... |
| types.py | N | ... |
| 源码 | N | ... |
| 测试 | N | ... |
| 模板 | N | ... |

## 核心合规状态
| 平台 | FAIL | WARN | INFO |
|------|------|------|------|

## 扩展合规状态
| 平台 | 扩展能力覆盖 | Agent字段覆盖 | 特性覆盖 | 权限覆盖 | 模型覆盖 |
|------|-------------|-------------|---------|---------|---------|

## 测试结果
passed: N / total: N

## 已知局限
- <在审计后填写：每条说明哪个平台的哪个能力文档不完整及其影响>
```
