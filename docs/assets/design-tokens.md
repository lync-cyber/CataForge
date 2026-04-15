# CataForge 文档图表 Design Tokens

所有 `docs/assets/*.svg` 必须引用本文件声明的 tokens，保证视觉一致。
风格定位：**技术蓝图 / 编辑印刷** — 暖纸色、近直角、等宽字体、琥珀单色点缀。
与主流 AI 产品（slate + sky/indigo + 大圆角 + Inter 无衬线）刻意区隔。

## 色板（Palette）

| Token              | 色值       | 用途                                          |
|--------------------|-----------|----------------------------------------------|
| `--surface`        | `#fdfcf7` | 卡片背景（暖纸色）— 明暗主题下均可读           |
| `--surface-accent` | `#fdf3d7` | 强调卡片背景（琥珀洗色）                       |
| `--ink`            | `#1c1917` | 主文字、粗边框                                 |
| `--ink-muted`      | `#57534e` | 次级文字                                       |
| `--rule`           | `#a8a29e` | 分隔线、细边框、箭头主体                       |
| `--accent`         | `#b45309` | 强调色（琥珀 700）— 索引数字、强调描边         |
| `--accent-ink`     | `#7c2d12` | 强调文字（在 `--surface-accent` 上）           |

> **不使用**：sky/indigo/violet/teal/cyan 家族、柔和粉彩、渐变填充、阴影、彩色阴影、任何 glow 效果。

## 尺寸与形状（Shape）

| Token             | 值        | 说明                               |
|-------------------|-----------|-----------------------------------|
| `--radius-box`    | `2`       | 卡片圆角（px）— 近直角，非 AI 圆胖 |
| `--radius-node`   | `9`       | 索引圆点半径                        |
| `--stroke-thin`   | `1`       | 细线                               |
| `--stroke-emph`   | `1.6`     | 强调描边                            |
| `--grid`          | `20`      | 基础网格步长（用于对齐）            |

## 字体（Typography）

全图统一等宽字体，传递"技术规格书"气质；不使用 Inter / sans AI-UI 字体。

| Token              | 字体栈                                                                     | 用途        |
|--------------------|---------------------------------------------------------------------------|------------|
| `--font-mono`      | `ui-monospace, 'SFMono-Regular', Menlo, Consolas, 'Liberation Mono', monospace` | 全部正文与标签 |

| Role              | Size  | Weight | Letter-spacing |
|-------------------|-------|--------|----------------|
| Stage index       | `10`  | `700`  | `1.2`          |
| Stage title       | `14`  | `700`  | `0`            |
| Stage subtitle    | `11`  | `400`  | `0`            |
| Caption / footer  | `10`  | `400`  | `0.4`          |

## 组件约定（Components）

- **卡片（card）**：`fill=var(--surface)` `stroke=var(--rule)` `stroke-width=1` `rx=2`。
- **强调卡片（card-emph）**：`fill=var(--surface-accent)` `stroke=var(--accent)` `stroke-width=1.6` `rx=2`。
- **索引节点（index node）**：半径 9 圆，`fill=var(--surface)` `stroke=var(--accent)` `stroke-width=1.4`，内部数字为 `--accent` 色。
- **连线（connector）**：直角或 90° 折线，`stroke=var(--rule)` `stroke-width=1`，箭头端用 `marker-end`。严禁曲线或贝塞尔。
- **背景底栅（optional）**：点阵 `r=0.6` `fill=var(--rule)` 间距 20px，整体不透明度 0.35。用于大幅图增强工程图纸感。

## 可读性守则

- 所有文字 `fill` 必须是 `--ink` / `--ink-muted` / `--accent-ink`，不依赖 `currentColor`（外链 SVG 不生效）。
- 卡片 `fill` 必须显式给出不透明浅色，保证在 GitHub 暗色主题下卡片自带前景。
- `viewBox` 必须声明，不写 `width/height` 硬值，确保 README 中按容器缩放。
- 仅使用 `<rect> <circle> <line> <path> <text> <marker>`；不使用 `<filter>` 阴影、不使用位图。
