/**
 * 可用字体名称列表（见 `/settings/appearance`）。
 * 此数组用于生成动态字体类（如 `font-inter`、`font-manrope`）。
 *
 * 📝 新增字体（Tailwind v4+）：
 * 1. 在此添加字体名称。
 * 2. 在 'index.html' 的 `<link>` 标签中引入新字体（Google Fonts 或其他来源）。
 * 3. 在 'index.css' 中通过 `@theme inline` 与 `font-family` CSS 变量添加字体族。
 *
 * 示例：
 * fonts.ts           → 在此数组中添加 'roboto'。
 * index.html         → 添加 Roboto 的 Google Fonts 链接。
 * index.css          → 在 CSS 中添加新字体，例如：
 *   @theme inline {
 *      // ... 其他字体族
 *      --font-roboto: 'Roboto', var(--font-sans);
 *   }
 */
export const fonts = ['inter', 'manrope', 'system'] as const
