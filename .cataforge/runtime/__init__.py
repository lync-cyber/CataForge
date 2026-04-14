"""CataForge Cross-Platform Runtime — 可执行工具层。

提供:
- profile_loader: 加载平台 profile 和 tool_map
- template_renderer: 基础模板 + override 合并
- result_parser: Agent 返回值容错解析
- frontmatter_translator: AGENT.md 能力标识符翻译
- hook_bridge: Hook 配置翻译与退化计算
- deploy: 部署编排
"""
