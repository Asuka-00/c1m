/** 打标页面公用：错误提示、幂等键绑定、权限码。 */
import { useRef } from 'react'
import { AxiosError } from 'axios'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import {
  markingApi,
  ruleFromConfig,
  traceCodeErrors,
  type TraceCodeReason,
  type TraceRule,
} from '@/lib/api/mes/marking'
import { newEventId } from '@/features/mes/common/event-id'
import { mesErrorMessage } from '@/features/mes/common/required'

/** 打标权限码（D79-7；追溯沿用 mes.exec:read）。 */
export const MARKING_PERM = {
  /** 模板与作业的读 */
  read: 'mes.marking:read',
  /** 模板编辑 / 新建版本 */
  templateWrite: 'mes.marking_template:write',
  /** 模板审批 / 退役 */
  templateApprove: 'mes.marking_template:approve',
  /** 打印、检验 */
  exec: 'mes.marking:exec',
  /** 作废（D78 补充三，与 exec 分开） */
  void: 'mes.marking:void',
} as const

/** 409 业务码（D78/D79）。 */
export const MARKING_CODES = [
  'template_readonly',
  'draft_exists',
  'invalid_transition',
  'marking_template_missing',
  'already_marked',
  'trace_code_mismatch',
  'no_active_marking',
  'check_blocked',
] as const

type Item = {
  loc?: string[]
  type?: string
  code?: string
  ctx?: Record<string, unknown>
}

/** 打标接口错误的本地化提示；不认识的交给通用 mesErrorMessage。 */
export function markingErrorMessage(err: unknown): string {
  if (err instanceof AxiosError && err.response) {
    const d = (err.response.data as { detail?: unknown })?.detail
    if (d && typeof d === 'object' && !Array.isArray(d)) {
      const o = d as { code?: string; ctx?: Record<string, unknown> }
      const ctx = o.ctx ?? {}
      if (o.code === 'check_blocked' && ctx.check === 'marking_inspection')
        return t('mes.marking.code.inspect_blocked')
      if (o.code && (MARKING_CODES as readonly string[]).includes(o.code))
        return t(`mes.marking.code.${o.code}`, {
          expected: String(ctx.expected ?? ''),
          actual: String(ctx.actual ?? ''),
        })
    }
    if (Array.isArray(d)) {
      const msgs = (d as Item[]).map((x) => {
        const type = x.type ?? x.code
        const field = x.loc?.[x.loc.length - 1] ?? ''
        if (type === 'idempotency_key_reused')
          return t('mes.marking.code.idempotency_key_reused')
        if (type === 'missing' && x.loc?.[0] === 'header')
          return t('mes.marking.code.key_missing')
        if (
          type === 'missing' &&
          (field === 'reason_id' || field === 'comment')
        )
          return t(`mes.marking.err.${field}Required`)
        // D79-2：自批 422 value_error ctx.reason=self_approval
        if (type === 'value_error' && x.ctx?.reason === 'self_approval')
          return t('mes.marking.err.selfApproval')
        // D79-1：白名单外占位符
        if (type === 'value_error' && x.ctx?.reason === 'unknown_placeholder')
          return t('mes.marking.err.unknownPlaceholder', {
            name: `{${String(x.ctx.placeholder ?? '')}}`,
          })
        if (
          type === 'value_error' &&
          (x.ctx?.reason === 'max_length' || x.ctx?.reason === 'pattern')
        )
          return traceReasonText(x.ctx.reason, Number(x.ctx.max_length))
        if (type === 'value_error' && x.ctx?.max_places != null)
          return t('mes.marking.err.maxPlaces', {
            n: String(x.ctx.max_places),
          })
        return null
      })
      if (msgs.every(Boolean)) return msgs.join('；')
    }
  }
  return mesErrorMessage(err, undefined)
}

/**
 * Idempotency-Key 绑定（D57/D78 Q6）：同一请求体重试沿用同一个 key（服务端返回原结果、不占新 seq）；
 * 请求体变了换新 key，避免 422 idempotency_key_reused。
 */
export function useIdemKey() {
  const ref = useRef<{ sig: string; key: string } | null>(null)
  return (sig: string) => {
    if (!ref.current || ref.current.sig !== sig)
      ref.current = { sig, key: newEventId() }
    return ref.current.key
  }
}

/** 追溯码单条错误文案。 */
export const traceReasonText = (r: TraceCodeReason, n: number) =>
  r === 'missing'
    ? t('mes.marking.err.traceRequired')
    : t(`mes.marking.err.trace_${r}`, { n: Number.isFinite(n) ? n : 32 })

/** 追溯码逐条错误文案（违反几条显示几条）。 */
export const traceErrorTexts = (v: string, rule: TraceRule) =>
  traceCodeErrors(v, rule).map((r) => traceReasonText(r, rule.maxLength))

/** 追溯码校验规则：以 GET /mes/marking/config 为准，取不到用默认（≤32、^[A-Z0-9-]+$）。 */
export function useTraceRule(): TraceRule {
  return useTraceConfig().rule
}

/** 规则 + 配置正则是否非法（非法时不做格式预校验，页面提示以后端为准）。 */
export function useTraceConfig(): { rule: TraceRule; patternInvalid: boolean } {
  const q = useQuery({
    queryKey: ['mes', 'marking', 'config'],
    queryFn: markingApi.config,
    retry: false,
    staleTime: 5 * 60_000,
  })
  const rule = ruleFromConfig(q.data)
  return { rule, patternInvalid: rule.pattern === null }
}
