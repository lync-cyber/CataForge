# CataForge SVG 再生成 Prompt 模板

新图或重新生成现有图时，从这里复制起手式 prompt，替换 `<<...>>` 占位即可。模板把视觉一致性、无障碍要求、禁用元素打包成单一 prompt，保证全文档共用同一套 design tokens。

## 起手式

```
生成 CataForge "<<图主题，例如：质量门禁三层结构>>" 示意图。

风格定位：技术蓝图 / 编辑印刷。暖纸色背景、近直角、等宽字体、琥珀单色点缀。
设计 tokens 取自 docs/assets/design-tokens.md：
  - 背景         #fdfcf7（暖纸色）
  - 强调背景     #fdf3d7（琥珀洗色）
  - 主文字       #1c1917
  - 次级文字     #57534e
  - 分隔线       #a8a29e
  - 强调色       #b45309（琥珀 700）— 索引数字与强调描边
  - 强调文字     #7c2d12（在强调背景上）
字体：ui-monospace, 'SFMono-Regular', Menlo, Consolas, 'Liberation Mono', monospace。

尺寸：viewBox <<W>>×<<H>>。不写 width/height 硬值。

内容：
  <<节点 / 流程 / 标注列表，每项一行，按视觉从上到下或左到右顺序>>

布局：
  <<结构（垂直流程图 / 水平流水线 / 网格 / 表格状对照）+ 视觉层级>>

可访问性：
  - 顶层 <title> 写图标题；<desc> 一句话总结图意。
  - 所有文字 fill 显式给 --ink / --ink-muted / --accent-ink，不依赖 currentColor。

禁止：
  - 渐变、阴影、glow、彩色阴影、滤镜效果
  - 曲线 / 贝塞尔（连线一律直角或 90° 折线）
  - emoji、卡通插画、人物图形
  - sky / indigo / violet / teal / cyan / pink 等 AI-UI 配色
  - <filter>、位图嵌入

输出：完整 SVG（含 <?xml version 头与 xmlns），文件头部以
<!-- prompt: ... --> 注释保留本 prompt 全文（去掉占位替换前的
<<>>），便于下次维护按 prompt 重生成。
```

## 注释格式

生成的 SVG 文件必须在 `<title>` / `<desc>` 之后追加：

```xml
<!--
  prompt-version: 1.0
  last-regenerated: <<YYYY-MM-DD>>
  prompt: |
    <<把上方起手式去除占位符后逐行粘贴到这里>>
-->
```

`prompt-version` 让未来若模板演进可识别旧版；`last-regenerated` 为审计提供时间锚。

## 工作流

1. 复制本文件起手式 → 改 `<<图主题>>` / `<<节点列表>>` / `<<布局>>` / `<<尺寸>>`
2. 喂给 LLM 生成 SVG
3. 把改完的 prompt 全文粘进 SVG 文件头注释
4. 提交 SVG 时检查：
   - `<title>` / `<desc>` 与 [docs/README.md](../README.md) §视觉资产 表对应
   - design tokens 色值与 [design-tokens.md](./design-tokens.md) 一致
   - 文件头注释含完整 prompt（pre-commit / CI 暂未自动校验，靠 reviewer 把关）

## 修改现有图

```text
1. 打开 docs/assets/<name>.svg
2. 取出文件头注释里的 prompt
3. 改"内容"或"布局"段
4. 重新生成 SVG
5. 替换 SVG 文件，同步更新注释里的 last-regenerated 与改动后的 prompt
```

## 反例

不允许的做法：

- 手编辑 SVG 的 `<rect>` / `<text>` 但不更新文件头 prompt。下次按旧 prompt 再生成会丢失改动。
- 在 prompt 里写"参考其它图风格"——必须显式引用本模板与 design-tokens.md，避免 LLM 幻觉出新颜色。
- 跳过 `<title>` / `<desc>`。无障碍工具与文档索引都需要它们。

## 参考

- design tokens 单一来源：[design-tokens.md](./design-tokens.md)
- SVG 资产规范（贡献流程角度）：[../contributing.md](../contributing.md) §SVG 资产规范
- 现有图清单：[../README.md](../README.md) §视觉资产
