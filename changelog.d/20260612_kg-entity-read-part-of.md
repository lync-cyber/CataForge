### Fixed

- **kg-first 实体级读取不再产出空壳卡片** —— 实体 SPARQL 经 `source_doc` + `source_section` JOIN 源 Section 节点绑定 `narrative_body`，`cataforge docs load "prd#§N.F-XXX"` 渲染的实体卡现包含源章节正文；Feature 卡经 `cf:part_of` 入边列出其 AcceptanceCriteria 子实体（不再依赖显式 xref 的 `cf:satisfies`），AC 卡新增 Part Of 段列出父实体。KG 渲染产物既无正文也无子实体内容时，loader 自动回退文件后端抽取，保证调用方拿到的信息量不低于文件后端。
- **`cataforge kg trace` 沿 `cf:part_of` 聚合** —— downstream 收集 part_of 入边子实体（AC 进入 `acceptance_criteria` 桶），upstream 沿 part_of 出边回到父实体；`coverage_status` 仍仅由 impl / test 桶决定，AC 桶不参与。
