/** 文本筛选的防抖时长（毫秒）。 */
export const SEARCH_DEBOUNCE_MS = 300

/** 下拉筛选的选项。 */
export interface FilterOption {
  value: string
  label: string
}

/** 声明式 DataTable 筛选。每个筛选对应同名的 URL 查询参数，
 *  并作为查询参数与分页 / 排序一起发送给列表接口。
 *  - text：自由文本（防抖）；名称用 'q' 表示接口的关键字搜索
 *  - select：可枚举值；静态 `options` 或异步 `loadOptions` */
export type FilterDef =
  | { type: 'text'; name: string; placeholder?: string }
  | {
      type: 'select'
      name: string
      /** “全部”选项的标签，如 "All roles" */
      label: string
      options?: FilterOption[]
      loadOptions?: () => Promise<FilterOption[]>
      /** loadOptions 的 react-query key（默认 ['filter-options', name]） */
      optionsKey?: unknown[]
    }

/** 所有表格的默认筛选：一个绑定 ?q= 的关键字搜索框 */
export const DEFAULT_FILTERS: FilterDef[] = [{ type: 'text', name: 'q' }]

/**
 * 关键字搜索筛选（绑定 ?q=）。
 *
 * @param placeholder - 输入框占位文本，缺省使用通用“搜索”文案
 */
export const searchFilter = (placeholder?: string): FilterDef => ({
  type: 'text',
  name: 'q',
  placeholder,
})

/**
 * 布尔筛选的两个选项（true / false）。
 *
 * @param yes - true 的标签
 * @param no - false 的标签
 */
export const boolOptions = (yes: string, no: string): FilterOption[] => [
  { value: 'true', label: yes },
  { value: 'false', label: no },
]
