/**
 * 撤销单位转换（F4-02 / P2）的纯函数：已撤销判断、409 原因文案。
 *
 * 后端 86ca4a1：`POST /mes/exec/transform/{id}/undo`（mes.exec:transform，体 reason_id / comment），
 * 子批都未动过才可撤销，否则 409 `transform_undo_blocked`，`lots` 逐批给出原因；成功后母批写履历
 * `transform_undo`（details 为转换快照，含 transform_id、children）。
 * D54（a7f7c9b）：保留转换记录并加 `undone_at` / `undone_by` / `undo_reason`；再次撤销 409（`lots` 为空）；
 * 撤销履历 details 带 `carrier_restored=false`（载具不恢复）。两种形态都识别。
 */
import { AxiosError } from 'axios'
import { fmtDateTime, t } from '@/i18n'
import type { MesRow } from '@/lib/api/mes/common'
import { mesErrorMessage } from '@/features/mes/common/required'

export interface UndoneInfo {
  at: string | null
  by: string | null
  reason: string | null
}

const det = (r: MesRow) => (r.details ?? {}) as Record<string, unknown>
const str = (v: unknown) => (v == null || v === '' ? null : String(v))

/** 转换记录的 id（履历 details.transform_id）。 */
export const transformIdOf = (r: MesRow) => str(det(r).transform_id)

/**
 * 一条转换履历是否已撤销：
 * D54 形态看 details.undone_at；86ca4a1 形态看同批履历里有没有同一 transform_id 的 transform_undo。
 */
export function undoneInfo(row: MesRow, rows: MesRow[]): UndoneInfo | null {
  if (row.action !== 'transform') return null
  const d = det(row)
  if (d.undone_at)
    return {
      at: str(d.undone_at),
      by: str(d.undone_by_label ?? d.undone_by),
      reason: str(d.undo_reason),
    }
  const id = transformIdOf(row)
  const u = id
    ? rows.find((r) => r.action === 'transform_undo' && transformIdOf(r) === id)
    : undefined
  if (!u) return null
  return {
    at: str(u.at),
    by: str(u.username),
    reason: str(u.reason_label ?? u.comment),
  }
}

/** 已撤销说明：「已撤销 · 时间 · 操作人 · 原因」。 */
export function undoneText(u: UndoneInfo): string {
  return [t('mes.tundo.undone'), u.at && fmtDateTime(u.at), u.by, u.reason]
    .filter(Boolean)
    .join(' · ')
}

/** 409 transform_undo_blocked → 逐批原因；其他错误 → 通用文案。 */
export function undoErrorLines(e: unknown): string[] {
  if (e instanceof AxiosError && e.response?.status === 409) {
    const d = (e.response.data as { detail?: unknown })?.detail as
      | Record<string, unknown>
      | undefined
    if (d && d.code === 'transform_undo_blocked') {
      const lots = (d.lots as { lot_code?: string; reason?: string }[]) ?? []
      // 按错误码判断（不看英文 message）：契约里 lots 为空即“已撤销再撤”
      if (!lots.length) return [t('mes.tundo.already')]
      return lots.map((l) =>
        t('mes.tundo.blocked', {
          lot: l.lot_code ?? '',
          reason: t(`mes.tundo.why.${l.reason ?? 'other'}`, {
            defaultValue: l.reason ?? '',
          }),
        })
      )
    }
  }
  if (e instanceof AxiosError && e.response?.status === 404)
    return [t('mes.tundo.notFound')]
  return [mesErrorMessage(e, undefined)]
}

/** 撤销履历行（transform_undo）：撤销时间 / 撤销人 / 撤销原因，及载具未恢复说明。 */
export function undoRowInfo(
  r: MesRow
): { info: string; carrier: boolean } | null {
  if (r.action !== 'transform_undo') return null
  const d = det(r)
  const at = str(d.undone_at ?? r.at)
  return {
    info: t('mes.tundo.info', {
      at: at ? fmtDateTime(at) : '—',
      by: str(d.undone_by ?? r.username) ?? '—',
      reason: str(d.undo_reason ?? r.reason_label ?? r.comment) ?? '—',
    }),
    carrier: d.carrier_restored === false,
  }
}
