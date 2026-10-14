/** 打标页面公用：错误提示、幂等键绑定、权限码。 */
import { useRef } from 'react'
import { AxiosError } from 'axios'
import { t } from '@/i18n'
import { newEventId } from '@/features/mes/common/event-id'
import { mesErrorMessage } from '@/features/mes/common/required'

/** 打标权限码（p3-tasks B1/B2；追溯沿用 mes.trace:read）。 */
export const MARKING_PERM = {
  read: 'mes.marking:read',
  write: 'mes.marking:write',
  approve: 'mes.marking:approve',
  exec: 'mes.marking:exec',
} as const

/** 409 业务码（mock 与后端同名；self_approval / template_readonly / draft_exists / already_marked 待后端确认）。 */
export const MARKING_CODES = [
  'self_approval',
  'template_readonly',
  'draft_exists',
  'invalid_transition',
  'marking_template_missing',
  'already_marked',
  'trace_code_mismatch',
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
