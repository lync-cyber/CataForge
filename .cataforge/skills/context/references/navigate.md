# context · navigate(读取与依赖展开)

按需加载文档章节/条目,解析依赖链,控制 token 预算。后端(图/文件)由框架路由,调用方式不变。

## 加载章节
```bash
cataforge context read <ref> [<ref> ...]
```
- `ref` 为 `doc_id#§N[.item]`(如 `prd#§2.F-001`、`arch#§1`)
- 仅输出目标章节(含嵌套子节);批量调用优于循环单次
- 退出码: 0=全部成功,2=至少一个引用失败(stderr 给原因)

可选标志:
- `--json` — 结构化数组,避免分隔符冲突
- `--with-deps` — 附带前置依赖章节(深度上限 2)
- `--budget N` — token 预算,超额 ref 转 stderr `[DEFERRED]`

## 查看索引
项目文档总览读 `docs/.doc-index.json` 的 `documents` 字段;缺失时运行 `cataforge context index`。

## 校验索引
```bash
cataforge context validate
```
只读校验;exit 0=干净,3=需 `cataforge context index` 重建。

## Bash 不可用时的降级
未获 Bash 权限的 Agent(architect / ui-designer / product-manager 等):读 `docs/.doc-index.json` 取目标文件的 `line_start`/`line_end`,用 Read + offset/limit 精确读取;`.doc-index.json` 不存在则委派给可执行 Bash 的 agent 重建。严禁一次性 Read 整篇超 200 行的文档。
