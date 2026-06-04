### Fixed

- **部署的 CLAUDE.md / AGENTS.md `框架版本` 字段现自动盖入已安装包版本** —— `cataforge deploy` 把指令文件模板里的 `{FRAMEWORK_VERSION}` 占位符渲染为 `cataforge.__version__`，并通过 section-merge `always_overwrite_fields` 在每次重新部署时刷新。

此前 `框架版本` 是静态描述文本、没有任何确定性写入路径（唯一写入者是升级 skill 的 AI Edit，纯 CLI 升级路径拿不到），导致升级后版本号停留在占位文本或首次部署的旧值，与 `framework.json.version` 漂移。现与 `运行时` 字段、`framework.json.version` 盖版本同等确定性：占位符 `{FRAMEWORK_VERSION}` 注册进渲染器，四平台 profile 的 `always_overwrite_fields.项目信息` 追加 `框架版本`。
