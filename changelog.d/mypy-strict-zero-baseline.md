### Changed

- **mypy 全局 strict 门禁** —— `[tool.mypy]` 改为全局 `strict = true`，覆盖整个 `cataforge.*`；新包默认就在 strict 下、无需 opt-in 登记，全树类型基线收敛到 0 error。CI `test.yml` 的 mypy step 从「全仓 informational + 单包 gate」改为单一阻塞的 `mypy src/cataforge`，任何新类型错误都会让 PR 失败。仅两处豁免：`_generated` codegen（`ignore_errors`，手改注解会被重新生成覆盖）与 3 个无 stub 第三方库 `pyshacl` / `linkml_runtime` / `docker`（`ignore_missing_imports`）。动态边界（pyoxigraph 查询结果、jinja render、entry-point 加载）统一经一个 `_sparql_utils.select_rows()` helper 或局部 `cast` 收窄。

### Removed

- **运行时依赖瘦身** —— `pytest` / `pytest-cov` 从 `[project.dependencies]` 移除（运行时零 import，仅测试用），保留在 `dev` extra；下游 `pip install cataforge` 不再拉入测试框架。
