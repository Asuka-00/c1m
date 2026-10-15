import axios, { AxiosError } from 'axios'
import i18n, { currentLanguage, t } from '@/i18n'
import { TENANT_WORDING } from '@/i18n/workspace-wording'
import { useAuthStore } from '@/stores/auth-store'
import { isPlatformPath } from '@/lib/space'

/** 后端 API 地址（VITE_API_URL；设为空字符串时使用同源，生产经 nginx 反代 /api；未设置时默认 http://localhost:8000）。 */
export const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

/** Axios 实例：附带 Bearer 令牌与 X-Tenant-ID；401 时登出。 */
export const http = axios.create({ baseURL: `${API_URL}/api/v1` })

http.interceptors.request.use((config) => {
  const { accessToken, tenantId } = useAuthStore.getState()
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  if (tenantId) config.headers['X-Tenant-ID'] = tenantId
  config.headers['Accept-Language'] = currentLanguage()
  return config
})

http.interceptors.response.use(
  (r) => r,
  (error: AxiosError) => {
    const status = error.response?.status
    const url = error.config?.url ?? ''
    const detail = (error.response?.data as { detail?: string })?.detail
    const st = useAuthStore.getState()
    // 模拟令牌过期 / 失效：恢复原平台令牌并回到平台租户列表，而不是登出
    if (
      st.originalToken &&
      (status === 401 || detail === 'Could not validate credentials')
    ) {
      st.endImpersonation()
      window.location.assign('/platform/tenants')
      return Promise.reject(error)
    }
    if (status === 401 || (status === 403 && url.includes('/users/me'))) {
      useAuthStore.getState().reset()
      if (!window.location.pathname.startsWith('/sign-in')) {
        const redirect = encodeURIComponent(window.location.pathname)
        window.location.assign(`/sign-in?redirect=${redirect}`)
      }
    }
    // 所选租户已不存在 / 已非成员 -> 回退到默认租户解析
    if (
      status === 404 &&
      (error.response?.data as { detail?: string })?.detail ===
        'Tenant not found' &&
      !url.startsWith('/tenants/')
    ) {
      useAuthStore.getState().setTenantId(null)
    }
    return Promise.reject(error)
  }
)

/** 把 API 错误转换为可读的多语言消息。已知的后端
 *  `detail` 字符串会被翻译（backend.<detail>）；否则回退为
 *  按状态码的翻译消息，最后才是原始 detail。 */
/**
 * 把接口错误转换为当前语言的提示文本。
 */
/**
 * 查询参数类 422 的本地化（D65 / 460df8f）：后端改为列表 `{loc:["query", 参数], msg}`，
 * 旧后端是字符串 detail。两种都按英文消息识别 sort_by 与「不是文本筛选字段」，否则 null。
 */
export function queryErrorText(msg: string): string | null {
  const s = msg.trim()
  const sort = /^sort_by must be one of: (.*)$/.exec(s)
  if (sort) return t('errors.query.sortBy', { list: sort[1] })
  const txt = /^(\S+) is not a text filter$/.exec(s)
  if (txt) return t('errors.query.notTextFilter', { field: txt[1] })
  return null
}

/** 一条查询 / 路径参数 422（loc 以 query 或 path 开头）的文案：已知消息本地化，否则「参数: 原消息」。 */
export function queryItemText(x: ParamItem): string {
  const known = queryErrorText(String(x.msg ?? ''))
  if (known) return known
  const name = paramName(x)
  // D77 补充二 / 三：无法解析的日期 → 422 value_error ctx.reason=pattern，loc=["query", 字段名]（旧 type=pattern 兼容）
  if (
    x.code === 'pattern' ||
    x.type === 'pattern' ||
    ([x.code, x.type].includes('value_error') && x.ctx?.reason === 'pattern')
  )
    return t('errors.query.pattern', { field: name })
  const m = paramMessage(x)
  return name ? `${name}: ${m}` : m
}

type ParamItem = {
  loc?: unknown[]
  msg?: string
  code?: string
  type?: string
  ctx?: Record<string, unknown>
}

/** 参数类 422 的参数名（loc[1..] 用 . 连接）。 */
export const paramName = (x: ParamItem) =>
  (x.loc ?? []).slice(1).map(String).join('.')

/** 参数类 422 的文案（不含参数名）：先 code 再 type 取固定码文案，否则去掉「参数名:」前缀的原消息。 */
export function paramMessage(x: ParamItem): string {
  const c = codeItemText(x)
  if (c) return c
  const msg = String(x.msg ?? '')
  const known = queryErrorText(msg)
  if (known) return known
  const name = paramName(x)
  return name && msg.startsWith(`${name}:`)
    ? msg.slice(name.length + 1).trim()
    : msg
}

/** loc 第一段为 query / path（D65 补充 2）：参数错误，不映射到表单字段。 */
export const isParamLoc = (x: { loc?: unknown[] }) =>
  x?.loc?.[0] === 'query' || x?.loc?.[0] === 'path'

/** 422 列表项带固定码（code / type）且有翻译时返回文案，否则 null。 */
export function codeItemText(x: {
  loc?: unknown[]
  code?: string
  type?: string
  ctx?: Record<string, unknown>
}): string | null {
  const ctx = ctxVars(x?.ctx)
  // D72：小数位超限 422 value_error + ctx.max_places（旧码 too_many_decimals 兼容）
  const places = Number(ctx.max_places)
  if (
    [x?.code, x?.type].some(
      (c) => c === 'value_error' || c === 'too_many_decimals'
    ) &&
    Number.isInteger(places)
  )
    return t('mes.err.tooManyDecimals', { n: places })
  // D77 补充一：422 value_error + ctx.reason=range_inverted / timezone_required
  const reason = typeof x?.ctx?.reason === 'string' ? x.ctx.reason : ''
  if (
    [x?.code, x?.type].includes('value_error') &&
    (reason === 'range_inverted' || reason === 'timezone_required')
  )
    return t(`mes.err.code.${reason}`)
  // D77 补充三：value_error + ctx.reason=pattern（无法解析的日期 / 时间）
  if ([x?.code, x?.type].includes('value_error') && reason === 'pattern')
    return t('errors.query.pattern', {
      field: (x?.loc ?? []).slice(1).map(String).join('.'),
    })
  for (const c of [x?.code, x?.type]) {
    if (!c) continue
    // date_range_too_large：有 ctx.max_days 用带天数的文案，否则用不带天数的
    const name =
      c === 'date_range_too_large' && ctx.max_days == null
        ? 'date_range_too_large_nolimit'
        : c
    for (const k of [`errors.code.${name}`, `mes.err.code.${name}`])
      if (i18n.exists(k)) return t(k, ctx)
  }
  return null
}

/** ctx 插值变量：数组用「、」/「, 」连接，entity 换成实体名（mes.entity.*，没有时原样）。 */
function ctxVars(ctx: Record<string, unknown> | undefined) {
  const sep = currentLanguage() === 'en' ? ', ' : '、'
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(ctx ?? {}))
    out[k] = Array.isArray(v) ? v.map(String).join(sep) : v
  if (typeof out.entity === 'string') {
    const key = `mes.entity.${out.entity}`
    if (i18n.exists(key)) out.entity = t(key)
  }
  return out
}

export function errorMessage(e: unknown): string {
  if (e instanceof AxiosError) {
    if (!e.response) return t('errors.network')
    const status = e.response.status
    const d = (e.response.data as { detail?: unknown })?.detail
    if (typeof d === 'string') {
      const q = status === 422 ? queryErrorText(d) : null
      if (q) return q
      const key = `backend.${d}`
      if (i18n.exists(key)) return t(key)
      // 工作区不暴露多租户概念：未翻译且提到 tenant 的后端消息改为通用提示
      if (TENANT_WORDING.test(d) && !isPlatformPath(window.location.pathname))
        return status === 403 ? t('errors.forbidden') : t('errors.generic')
      return d
    }
    if (status === 422) {
      if (Array.isArray(d)) {
        // 架构定：所有 422 detail 都是列表，带固定码时按码取文案（mes.err.code.* / errors.code.*）
        const coded = d.map(codeItemText)
        if (d.length && coded.every(Boolean))
          return [...new Set(coded)].join('；')
        const isQ = isParamLoc
        // 全是查询参数错误：逐条本地化，不加“校验失败”前缀
        if (d.length && d.every(isQ)) return d.map(queryItemText).join('；')
        const msgs = d
          .map((x: { loc?: unknown[]; msg?: string }) =>
            isQ(x) ? queryItemText(x) : x.msg
          )
          .filter(Boolean)
        return `${t('errors.validation')} ${msgs.join(', ')}`.trim()
      }
      return t('errors.validation')
    }
    if (status === 403) return t('errors.forbidden')
    if (status >= 500) return t('errors.server')
    return e.message
  }
  return String(e)
}
