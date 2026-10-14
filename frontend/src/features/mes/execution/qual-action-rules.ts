/** 资质行操作的校验与请求体（B6 / D88）。 */
import { t } from '@/i18n'
import { QUAL_COMMENT_MAX } from '@/lib/api/mes/qual-history'

export type QualOp = 'deactivate' | 'renew' | 'reactivate'
interface QualActionValues {
  expires_on: string
  reason_id: string
  comment: string
  approved_by: string
}

const blank = (s: string) => !s.trim()

/** 前端先拦必填（后端仍以 422 为准）。 */
export function qualActionErrors(
  op: QualOp,
  v: QualActionValues
): Partial<Record<keyof QualActionValues, string>> {
  const e: Partial<Record<keyof QualActionValues, string>> = {}
  if (op === 'reactivate') return e
  if (blank(v.reason_id)) e.reason_id = t('mes.err.required')
  if (blank(v.comment)) e.comment = t('mes.err.required')
  else if ([...v.comment].length > QUAL_COMMENT_MAX)
    e.comment = t('mes.reticle.err.tooLong', { max: QUAL_COMMENT_MAX })
  if (op === 'renew' && blank(v.approved_by))
    e.approved_by = t('mes.err.required')
  return e
}

/** 请求体：停用 {is_active:false, reason_id, comment}；改有效期 {expires_on（空 = 永久 null）, reason_id, comment, approved_by}；
 *  恢复 {is_active:true}。D85 补充二：停用与改有效期不放在同一次请求。 */
export function qualActionBody(
  op: QualOp,
  v: QualActionValues
): Record<string, unknown> {
  if (op === 'reactivate') return { is_active: true }
  const base = { reason_id: v.reason_id, comment: v.comment.trim() }
  if (op === 'deactivate') return { is_active: false, ...base }
  return {
    expires_on: v.expires_on || null,
    ...base,
    approved_by: v.approved_by.trim(),
  }
}

/** QA P3-2：改有效期时新值与原值相同（含原本永久且仍留空）视为未修改，禁止保存 */
export function qualExpiresUnchanged(original: unknown, next: string): boolean {
  return String(original ?? '') === next
}
