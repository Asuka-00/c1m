import { getSiteTz, siteDayBoundary } from '@/lib/site-tz'

/** 文本筛选的防抖时长（毫秒）。 */
export const SEARCH_DEBOUNCE_MS = 300

/** 有默认值的筛选被用户显式选择“全部”时在 URL 中的取值。 */
export const ALL_VALUE = '*'

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
      /** 远程搜索选项（数据量大的引用字段）：按输入关键字分页查询 */
      search?: (q: string) => Promise<FilterOption[]>
      /** 远程模式下解析当前值的显示标签 */
      resolve?: (value: string) => Promise<string>
      /** 默认值：URL 无此参数时生效；选择“全部”时以 ALL_VALUE 显式记录 */
      defaultValue?: string
    }
  | {
      /** 日期范围：URL 参数为 `<name>_from` / `<name>_to`（YYYY-MM-DD） */
      type: 'daterange'
      name: string
      label: string
      /** 字段类型：datetime 时按本地时区转换为当日起止时刻发送 */
      kind?: 'date' | 'datetime'
    }

/** 筛选定义对应的 URL 参数名（日期范围展开为起止两个参数）。 */
export function filterKeys(def: FilterDef): string[] {
  return def.type === 'daterange'
    ? [`${def.name}_from`, `${def.name}_to`]
    : [def.name]
}

/** 浏览器本地日期（YYYY-MM-DD；业务日期请用 lib/site-tz 的站点日期）。 */
export function ymd(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/**
 * 日期范围参数转换为接口参数（D75）：
 * - datetime 字段：按站点时区算当天 00:00:00 / 23:59:59.999999，带偏移发送（后端不换算、两头都含）；
 * - date 字段：只取前 10 位，直接传站点日期。
 *
 * @param v - YYYY-MM-DD
 * @param end - 是否为上限
 * @param kind - 字段类型
 * @param tz - 站点时区（默认当前站点时区）
 */
export function rangeParam(
  v: string,
  end: boolean,
  kind: 'date' | 'datetime' = 'datetime',
  tz: string = getSiteTz()
): string {
  const ymd = v.trim().slice(0, 10)
  if (kind === 'date') return ymd
  return siteDayBoundary(ymd, end, tz)
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

/** 选项缓存键的专用后缀：保证与同前缀的数据查询（如 ['notifications', 'meta']）不冲突。 */
export const FILTER_OPTIONS_SUFFIX = '__filter-options'

/**
 * 下拉筛选选项的 react-query key：调用方的 `optionsKey`（缺省 ['filter-options', name]）
 * 末尾追加专用后缀。保留前缀以便按前缀失效，同时避免与页面中同键的数据查询共享缓存
 * （否则缓存中的非数组数据会被当作选项，导致渲染异常）。
 */
export function filterOptionsKey(def: {
  name: string
  optionsKey?: unknown[]
}): unknown[] {
  return [
    ...(def.optionsKey ?? ['filter-options', def.name]),
    FILTER_OPTIONS_SUFFIX,
  ]
}
