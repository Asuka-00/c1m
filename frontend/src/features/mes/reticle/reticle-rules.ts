/** 光罩动作规则：权限、可用状态、表单校验与 409 错误码三语提示（v0.8.2 §3.2）。 */
import { AxiosError } from 'axios'
import { t } from '@/i18n'
import type {
  Reticle,
  ReticleAction,
  ReticleActionInput,
  ReticleStatus,
} from '@/lib/api/mes/reticle'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import { mesErrorMessage } from '@/features/mes/common/required'

/** reason / comment / note 上限。 */
export const TEXT_MAX = 300
/** delta 小数位上限（D60；B4 422 value_error，ctx.max_places）。 */
export const MAX_PLACES = 6
/** storage_location 上限。 */
export const LOCATION_MAX = 64

type Field = 'delta' | 'reason' | 'comment' | 'inspection'
interface Spec {
  perm: string
  from: ReticleStatus[] | 'non_terminal'
  fields: Field[]
}

const NON_HOLD: ReticleStatus[] = [
  'available',
  'in_use',
  'dirty',
  'inspecting',
  'pending_maintenance',
]

/** 动作定义（顺序即按钮顺序）。 */
export const ACTIONS: Record<ReticleAction, Spec> = {
  usage: {
    perm: MES_PERM.reticleWrite,
    from: 'non_terminal',
    fields: ['delta'],
  },
  hold: { perm: MES_PERM.reticleWrite, from: NON_HOLD, fields: ['reason'] },
  release: {
    perm: MES_PERM.reticleWrite,
    from: ['on_hold'],
    fields: ['comment'],
  },
  'clean-start': {
    perm: MES_PERM.reticleWrite,
    from: ['available'],
    fields: ['comment'],
  },
  'clean-complete': {
    perm: MES_PERM.reticleWrite,
    from: ['dirty'],
    fields: ['comment'],
  },
  'repair-complete': {
    perm: MES_PERM.reticleWrite,
    from: ['pending_maintenance'],
    fields: ['comment'],
  },
  'inspect-start': {
    perm: MES_PERM.reticleWrite,
    from: ['available'],
    fields: ['comment'],
  },
  restore: {
    perm: MES_PERM.reticleOverride,
    from: ['pending_maintenance'],
    fields: ['reason'],
  },
  'life-reset': {
    perm: MES_PERM.reticleOverride,
    from: ['pending_maintenance'],
    fields: ['reason'],
  },
  scrap: {
    perm: MES_PERM.reticleOverride,
    from: 'non_terminal',
    fields: ['reason'],
  },
  /** 卸载（仍挂着时才可用；非 in_use 只关闭挂载记录） */
  unmount: {
    perm: MES_PERM.reticleWrite,
    from: 'non_terminal',
    fields: ['comment'],
  },
  /** 检查记录录入（D69 Q10：mes.reticle:write）；pass 仅 inspecting，fail 还可 on_hold */
  inspection: {
    perm: MES_PERM.reticleWrite,
    from: ['inspecting', 'on_hold'],
    fields: ['inspection', 'comment'],
  },
}

export const ACTION_LIST = Object.keys(ACTIONS) as ReticleAction[]

/** 有权限才显示按钮。 */
export function visibleActions(can: (p: string) => boolean) {
  return ACTION_LIST.filter((a) => can(ACTIONS[a].perm))
}

/** 当前状态是否允许该动作（只做界面提示，后端最终校验；挂载规则交给后端 409）。 */
export function actionEnabled(
  r: Pick<Reticle, 'status_code'> & Partial<Pick<Reticle, 'equipment_id'>>,
  a: ReticleAction
) {
  if (a === 'unmount' && !r.equipment_id) return false
  const from = ACTIONS[a].from
  return from === 'non_terminal'
    ? r.status_code !== 'scrapped'
    : from.includes(r.status_code)
}

/** 表单校验，返回 字段 → 错误文案。 */
export function validateAction(
  a: ReticleAction,
  v: ReticleActionInput
): Record<string, string> {
  const e: Record<string, string> = {}
  const tooLong = (s?: string) => (s ?? '').length > TEXT_MAX
  if (a === 'usage') {
    const raw = String(v.delta ?? '').trim()
    const d = Number(raw)
    if (!raw || !Number.isFinite(d) || d === 0)
      e.delta = t('mes.reticle.err.deltaNonZero')
    else if (!/^-?\d+(\.\d{1,6})?$/.test(raw))
      e.delta = t('mes.reticle.err.maxPlaces', { max: MAX_PLACES })
    else if (d < 0 && !(v.reason_id ?? '').trim())
      e.reason_id = t('mes.reticle.err.reasonIdRequired')
    if (tooLong(v.note))
      e.note = t('mes.reticle.err.tooLong', { max: TEXT_MAX })
  }
  if (a === 'inspection') {
    if (!v.kind) e.kind = t('mes.err.required')
    if (!v.result) e.result = t('mes.err.required')
    const dc = String(v.defect_count ?? '').trim()
    if (dc && !/^\d+$/.test(dc)) e.defect_count = t('mes.reticle.err.nonNegInt')
  }
  if (ACTIONS[a].fields.includes('reason')) {
    if (!(v.reason ?? '').trim()) e.reason = t('mes.err.required')
    else if (tooLong(v.reason))
      e.reason = t('mes.reticle.err.tooLong', { max: TEXT_MAX })
  }
  if (tooLong(v.comment))
    e.comment = t('mes.reticle.err.tooLong', { max: TEXT_MAX })
  return e
}

/** 库位校验（≤64）。 */
export function validateLocation(s: string) {
  return s.length > LOCATION_MAX
    ? t('mes.reticle.err.tooLong', { max: LOCATION_MAX })
    : null
}

/** 光罩专用 409 码。 */
export const RETICLE_CODES = [
  'invalid_transition',
  'life_limit_reached',
  'already_mounted',
  'still_mounted',
  'reticle_unavailable',
  'life_reached',
] as const

/** 错误提示：光罩 409 码 → 三语；其他交给通用 MES 处理。 */
export function reticleErrorMessage(err: unknown, action?: ReticleAction) {
  if (err instanceof AxiosError && err.response) {
    const d = (err.response.data as { detail?: unknown })?.detail
    // D71：超 6 位小数为 422 value_error，ctx 带 max_places
    if (Array.isArray(d)) {
      const mp = d.find(
        (x: { ctx?: { max_places?: unknown } }) => x?.ctx?.max_places != null
      ) as { ctx: { max_places: unknown } } | undefined
      if (mp) return t('mes.reticle.err.maxPlaces', { max: mp.ctx.max_places })
    }
    const code =
      d && typeof d === 'object' && !Array.isArray(d)
        ? (d as { code?: unknown }).code
        : undefined
    if (
      typeof code === 'string' &&
      (RETICLE_CODES as readonly string[]).includes(code)
    )
      return t(`mes.reticle.code.${code}`, {
        action: action ? actionLabel(action) : '',
      })
  }
  return mesErrorMessage(err, undefined)
}

/** 寿命进度（0–1，无上限为 null）。 */
export function lifeRatio(r: Pick<Reticle, 'shot_count' | 'max_shots'>) {
  if (r.max_shots == null || Number(r.max_shots) <= 0) return null
  return Number(r.shot_count) / Number(r.max_shots)
}

/** 动作 / 履历 action 枚举（下划线或连字符）→ 三语名称。 */
export function actionLabel(a: string) {
  if (a === 'system') return t('mes.reticle.system')
  const k = a.replace(/_/g, '-')
  return t(`mes.reticle.action.${k}`, { defaultValue: a })
}
