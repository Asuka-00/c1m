/**
 * 后端文本本地化：后端只返回错误码 + 参数（`{code, message, params}`，`message` 为英文兜底），
 * 文案在语言包 `error.yaml` 的 `error.code_<错误码>`；检查结果说明、系统说明按键翻译。
 */
import i18n, { t } from '@/i18n'

/** 一条检查结果说明：消息键（`<检查类型>.<键>`）+ 插值参数。 */
export interface MsgPart {
  key: string
  params?: Record<string, unknown>
}

/**
 * 逐条翻译检查结果说明（`mes.checkMsg.<key>`）并拼接；任一条缺译文时整体回退后端英文。
 *
 * @param parts - 后端 `msg_parts`
 * @param fallback - 后端英文 `message`
 */
export function partsText(
  parts: MsgPart[] | null | undefined,
  fallback: string
): string {
  if (!parts?.length) return fallback
  const keys = parts.map((p) => `mes.checkMsg.${p.key}`)
  if (!keys.every((k) => i18n.exists(k))) return fallback
  return parts
    .map((p, i) => t(keys[i], { ...p.params }))
    .join(t('mes.checkSep'))
}

/** 检查结果（或履历中的检查摘要）的本地化说明。 */
export function checkMessage(r: {
  message?: string | null
  msg_parts?: MsgPart[] | null
}): string {
  return partsText(r.msg_parts, r.message ?? '')
}

/** 错误详情里不属于插值参数的键。 */
const NON_PARAMS = new Set(['code', 'message', 'params', 'results', 'items'])

/** i18next 的选项键：不允许由服务端参数覆盖（语言、默认值、命名空间等）。 */
const RESERVED = new Set([
  'lng',
  'lngs',
  'fallbackLng',
  'ns',
  'defaultValue',
  'context',
  'returnObjects',
  'interpolation',
  'replace',
  'postProcess',
  'keySeparator',
  'nsSeparator',
  'joinArrays',
  'ordinal',
])

/** 去掉会影响翻译行为的 i18next 选项键。 */
export function safeParams(
  p: Record<string, unknown> | null | undefined
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(p ?? {}).filter(([k]) => !RESERVED.has(k))
  )
}

/**
 * 错误详情的插值参数：`params` 加上详情顶层的标量字段（如 `lot_code`、`action`）。
 */
export function detailParams(
  d: Record<string, unknown>
): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(d))
    if (!NON_PARAMS.has(k) && (typeof v === 'string' || typeof v === 'number'))
      out[k] = v
  return safeParams({
    ...out,
    ...(d.params as Record<string, unknown> | undefined),
  })
}

/**
 * 错误码文案（`error.code_<code>`）。
 *
 * @returns 本地化文案；不是数字错误码或没有译文时为 null
 */
export function codeText(
  code: unknown,
  params?: Record<string, unknown> | null
): string | null {
  if (typeof code !== 'number') return null
  const key = `error.code_${code}`
  return i18n.exists(key) ? t(key, safeParams(params)) : null
}

/** 后端错误项（422 字段错误 / 导入行错误）：`code` + `params`，另有字段位置信息。 */
export interface CodedItem {
  code?: unknown
  params?: Record<string, unknown> | null
  msg?: string
  loc?: unknown[]
  field?: string
  label_key?: string
}

/** 错误项对应的字段名（`field` 优先，其次 `loc` 中最后一个非数字的字符串）。 */
export function itemField(x: CodedItem): string {
  if (x.field) return x.field
  const names = (x.loc ?? []).filter(
    (p): p is string => typeof p === 'string' && p !== 'body'
  )
  return names[names.length - 1] ?? ''
}

/**
 * 错误项的本地化文案：译文里的 `{{field}}` 由 `label` 解析字段显示名（缺省为 `label_key` 的译文或原字段名），
 * `params.line` 存在时前缀“第 N 行”。
 *
 * @param label - 字段名 → 显示名（如实体字段标签）
 * @returns 本地化文案；没有错误码或没有译文时为 null
 */
export function itemText(
  x: CodedItem,
  label?: (name: string) => string
): string | null {
  const name = itemField(x)
  const shown =
    (x.label_key && i18n.exists(x.label_key) ? t(x.label_key) : null) ??
    (name ? (label?.(name) ?? name) : '')
  const text = codeText(x.code, { ...safeParams(x.params), field: shown })
  if (text === null) return null
  return x.params?.line != null
    ? t('mes.err.withLine', { line: x.params.line, text })
    : text
}

/** 系统生成的说明 `{key, params}`（`mes.sysNote.<key>`）；缺译文时返回 key。 */
export function noteText(
  note: { key?: string; params?: Record<string, unknown> } | null | undefined
): string {
  if (!note?.key) return ''
  const k = `mes.sysNote.${note.key}`
  return i18n.exists(k) ? t(k, { ...note.params }) : note.key
}

/**
 * 实体行中由系统生成的文本（检查日志说明、Hold / E10 履历的系统说明）的本地化显示。
 *
 * @param entity - 实体编码
 * @param field - 字段名
 * @param row - 行数据
 * @returns 本地化文本；该字段没有系统文本时为 null
 */
export function systemText(
  entity: string,
  field: string,
  row: Record<string, unknown>
): string | null {
  if (entity === 'check_log' && field === 'message') {
    const parts = (row.context as { msg_parts?: MsgPart[] } | null)?.msg_parts
    return parts?.length ? partsText(parts, String(row.message ?? '')) : null
  }
  if (
    (entity === 'lot_hold' || entity === 'e10_history') &&
    field === 'comment'
  ) {
    const note = row.note as { key?: string } | null
    if (!note?.key) return null
    return [noteText(note), row.comment].filter(Boolean).join(' · ')
  }
  return null
}
