### Changed

- **`adapter/platform/_deploy_mixins.py` 拆分为同名包** —— 855 行的单文件按部署关注点拆为 `_deploy_mixins/{agents,instructions,skills,commands_rules,mcp}.py`，每个 mixin 与其单一消费者的模块级 helper / 常量同处一文件；`__init__.py` 重导出五个 mixin 类，保持 `from cataforge.adapter.platform._deploy_mixins import ...` 的导入面不变。顺带把 overrides/rules 路径改为经 `ProjectPaths.platform_overrides` 派生。纯结构性改动，行为等价。
