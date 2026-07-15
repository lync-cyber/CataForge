### Fixed

- **`pip install cataforge` 开箱即败修复** —— wheel 运行时依赖不再携带 `linkml-runtime → prefixcommons → pytest-logging` 传递链（pytest-logging 仅有 2015 legacy sdist，在 Debian/Ubuntu 补丁版系统 setuptools 上构建即崩；`[tool.uv]` override 不进发布元数据、对 pip 消费者无效）。KG store bootstrap 改读包内 `subclass_axioms.ttl` 制品（非 governance 店过滤 `cfgov` 命名空间），linkml 工具链降至 `dev` extra（仅 schema codegen 使用），并新增运行时依赖契约测试防回归。
