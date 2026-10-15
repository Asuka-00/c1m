/**
 * 下拉框 / 数字框的统一宽度。
 * - FIELD_MIN_W：触发框最小宽度，保证「请选择…」/ Select… / 選択… 和常见编码不被截断。
 * - POPOVER_W：弹出层不比触发框窄，按最长选项撑开，上限 32rem（且不超出视口），超出换行。
 * - NUM_W：独立数字框（筛选栏、行内）统一宽度。
 */
export const FIELD_MIN_W = 'min-w-48'
export const POPOVER_W =
  'w-auto min-w-(--radix-popover-trigger-width) max-w-[min(32rem,calc(100vw-2rem))]'
export const NUM_W = 'w-32'
