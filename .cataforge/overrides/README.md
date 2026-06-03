# 覆盖层（overrides）

框架发货的 agent / skill 在 `.cataforge/agents/`、`.cataforge/skills/`，由 `cataforge upgrade apply` 全量刷新。要长期定制又不被升级覆盖，把改动放进本目录：

- `user/{agents,skills}/` —— 个人定制，最高优先级
- `project/{agents,skills}/` —— 团队共享定制

本目录不在 scaffold manifest 内，`upgrade apply` 永不触碰它。完整说明见 [`docs/reference/overrides.md`](../../docs/reference/overrides.md)。

## 优先级（高层胜出）

```
overrides/user/  >  overrides/project/  >  .cataforge/（发货层）  >  包内 builtin
```

## 两种粒度

1. 整文件覆盖：放完整 `AGENT.md` / `SKILL.md` 整体替换基线。改 frontmatter（`tools` / `model_tier` / `description` 等）必须走整文件覆盖。
2. section 补丁：放 `<name>.patch.md`，与基线同名的 `## ` 小节覆盖其正文，新的 `## ` 小节追加到末尾。

## 起步

从发货层导出一个起点再编辑，然后 `cataforge deploy` 落地：

```bash
cataforge override eject agents architect                                      # 整文件，project 层
cataforge override eject agents architect --layer user --patch --section "Execution Rules"
cataforge override list                                                        # 查看每个 asset 由哪些层定义
```

## 示例（section 补丁）

`project/agents/architect/AGENT.patch.md`：

```markdown
## Execution Rules
- 覆盖基线同名小节的正文

## 团队专属约定
- 新增小节，追加到末尾
```

skill 级 rules YAML（wiring / e2e）同样走覆盖层：`{project,user}/skills/<id>/rules/wiring-<lang>.yaml`。

> 本目录默认仅含本说明与空的 `project/`、`user/` 占位目录；放入实际覆盖文件后即生效。
