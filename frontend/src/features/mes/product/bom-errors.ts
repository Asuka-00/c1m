/** BOM 接口错误 → 本地化提示（不展示后端原始英文，D34 / D38）。 */
import { AxiosError } from 'axios'
import { t } from '@/i18n'

/** 字段级错误：`line` 为明细下标（从 0 开始，D38），主表字段为 null。 */
export interface BomFieldError {
  line: number | null
  field: string
  message: string
}

export interface BomError {
  /** 总提示 */
  message: string
  /** 能定位到字段的 422 */
  fields: BomFieldError[]
}

interface Item {
  loc?: unknown[]
  msg?: string
  type?: string
}

function fieldMessage(it: Item): string {
  const msg = it.msg ?? ''
  if (it.type === 'extra_forbidden' || /not writable|set by POST/.test(msg))
    return t('mes.bomTab.err.notWritable')
  if (/required|missing/i.test(msg) || it.type === 'missing')
    return t('mes.bomTab.err.required')
  if (/whole number/.test(msg)) return t('mes.bomTab.err.wholeNumber')
  if (/at least one line/.test(msg)) return t('mes.bomTab.err.noLines')
  if (/circular/.test(msg)) return t('mes.bomTab.err.circular')
  if (/levels/.test(msg)) return t('mes.bomTab.err.tooDeep')
  return t('mes.bomTab.err.invalid')
}

/** 解析 422 的 loc：去掉开头的 body；`["lines", 0, "qty"]` 定位到第 0 行。 */
export function parseLoc(loc: unknown[]): {
  line: number | null
  field: string
} {
  const p = loc[0] === 'body' ? loc.slice(1) : loc
  if (p[0] === 'lines' && typeof p[1] === 'number')
    return { line: p[1], field: String(p[2] ?? '') }
  return { line: null, field: String(p[0] ?? '') }
}

const CONFLICTS: [RegExp, string][] = [
  [/only draft BOMs can be changed/, 'mes.bomTab.err.readOnly'],
  [/only drafts can be activated/, 'mes.bomTab.err.notDraft'],
  [/already superseded/, 'mes.bomTab.err.superseded'],
  [/already void/, 'mes.bomTab.err.alreadyVoid'],
  [/same key already exists/, 'mes.bomTab.err.duplicateLine'],
]

/** 把 BOM 接口错误转成提示和字段错误。 */
export function bomError(e: unknown): BomError {
  if (!(e instanceof AxiosError))
    return { message: t('errors.generic'), fields: [] }
  if (!e.response) return { message: t('errors.network'), fields: [] }
  const { status } = e.response
  const d = (e.response.data as { detail?: unknown })?.detail
  // D34：403 只提示无权限，不暴露字段细节
  if (status === 403)
    return { message: t('mes.bomTab.noPermission'), fields: [] }
  if (status === 422) {
    const items = (Array.isArray(d) ? d : []) as Item[]
    const fields = items
      .filter((x) => Array.isArray(x.loc))
      .map((x) => ({ ...parseLoc(x.loc!), message: fieldMessage(x) }))
    const first = fields[0]
    return {
      message:
        fields.length === 1 && first.field === 'bom_line'
          ? first.message
          : t('mes.bomTab.err.validation'),
      fields,
    }
  }
  if (status === 409) {
    const s = typeof d === 'string' ? d : ''
    const hit = CONFLICTS.find(([re]) => re.test(s))
    return { message: t(hit ? hit[1] : 'mes.bomTab.err.conflict'), fields: [] }
  }
  if (status === 404)
    return { message: t('mes.bomTab.err.notFound'), fields: [] }
  if (status >= 500) return { message: t('errors.server'), fields: [] }
  return { message: t('errors.generic'), fields: [] }
}
