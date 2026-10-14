/** 光罩动作规则：权限、可用状态、表单校验与 409 错误码三语提示（v0.8.2 §3.2）。 */
import { AxiosError } from 'axios'
import i18n, { fmtDateTime, t } from '@/i18n'
import {
  tooFarInFuture,
  type Reticle,
  type ReticleAction,
  type ReticleActionInput,
  type ReticleStatus,
} from '@/lib/api/mes/reticle'
import { compareDecimal } from '@/lib/decimal'
import { siteWallToIso } from '@/lib/site-tz'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import { mesErrorMessage } from '@/features/mes/common/required'
import {
  toolLifeLevel,
  warnRatio,
  type ToolLifeLevel,
} from '@/features/mes/execution/tool-life'

/** reason / comment / note 上限。 */
export const TEXT_MAX = 300
/** delta 小数位上限（D60；B4 422 value_error，ctx.max_places）。 */
export const MAX_PLACES = 6
/** storage_location 上限。 */
export const LOCATION_MAX = 64

type Field =
  | 'delta'
  | 'reason'
  | 'comment'
  | 'inspection'
  | 'mount'
  | 'incident'
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
  /** 上机（MountIn，mes.reticle:write）：仅 available 且未挂载 */
  mount: {
    perm: MES_PERM.reticleWrite,
    from: ['available'],
    fields: ['mount', 'comment'],
  },
  /** 登记异常（IncidentIn，mes.reticle:write）：非 scrapped 一律转 on_hold(incident) + 待检 */
  incident: {
    perm: MES_PERM.reticleWrite,
    from: 'non_terminal',
    fields: ['incident'],
  },
}

/** 异常类型（IncidentIn.kind）。 */
export const INCIDENT_KINDS = ['collision', 'drop', 'other'] as const
/** slot_code 上限（MountIn）。 */
export const SLOT_MAX = 64

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
  if (a === 'mount' && r.equipment_id) return false
  const from = ACTIONS[a].from
  return from === 'non_terminal'
    ? r.status_code !== 'scrapped'
    : from.includes(r.status_code)
}

/** 禁用原因提示：scrapped 终态（D72 后端回 409 invalid_transition）。 */
export function disabledHint(r: Pick<Reticle, 'status_code'>) {
  return r.status_code === 'scrapped'
    ? t('mes.reticle.scrappedHint')
    : undefined
}

/** 表单校验，返回 字段 → 错误文案。 */
export function validateAction(
  a: ReticleAction,
  v: ReticleActionInput,
  now: number = Date.now()
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
  if (a === 'mount') {
    if (!(v.equipment_id ?? '').trim()) e.equipment_id = t('mes.err.required')
    if ((v.slot_code ?? '').length > SLOT_MAX)
      e.slot_code = t('mes.reticle.err.tooLong', { max: SLOT_MAX })
  }
  // D82：补录时间（站点墙上时间）比当前晚超过 5 分钟拦住
  const bf = (v as { backfill_at?: string }).backfill_at
  if (bf) {
    const iso = siteWallToIso(bf)
    if (!iso) e.backfill_at = t('mes.reticle.err.backfillInvalid')
    else if (tooFarInFuture(iso, now))
      e.backfill_at = t('mes.reticle.err.futureTime')
  }
  if (a === 'incident') {
    if (!(INCIDENT_KINDS as readonly string[]).includes(v.kind ?? ''))
      e.kind = t('mes.err.required')
    if (tooLong(v.description))
      e.description = t('mes.reticle.err.tooLong', { max: TEXT_MAX })
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
  // mount：同机台同槽位已有光罩
  'slot_occupied',
  // D82：补录时间早于最近一次下机 / 事件，或下机早于上机
  'time_out_of_order',
  // 409：上次同 key 请求仍在处理；重试时内容不变复用同一 key
  'idempotency_in_progress',
  // D72：有履历的光罩删除 → 409 referenced
  'referenced',
] as const
// 422 idempotency_key_reused（D57/D72）走通用 mesErrorMessage（mes.err.code.idempotency_key_reused）

/** 错误提示：光罩 409 码 → 三语；其他交给通用 MES 处理。 */
/** 409 time_out_of_order 的 latest_event_at（D82 补充三：409 上下文字段在 detail 顶层，不用 ctx）。 */
export function latestEventAt(err: unknown): string | null {
  if (!(err instanceof AxiosError)) return null
  const d = (err.response?.data as { detail?: unknown })?.detail as
    | { latest_event_at?: unknown }
    | undefined
  if (!d || typeof d !== 'object' || Array.isArray(d)) return null
  const v = d.latest_event_at
  return typeof v === 'string' && v ? v : null
}

export function reticleErrorMessage(err: unknown, action?: ReticleAction) {
  if (err instanceof AxiosError && err.response) {
    const d = (err.response.data as { detail?: unknown })?.detail
    // D71：超 6 位小数为 422 value_error，ctx 带 max_places
    if (Array.isArray(d)) {
      // D80：缺 Idempotency-Key / 同 key 换请求体
      const items = d as { loc?: unknown[]; type?: string; code?: string }[]
      // D82：补录时间超前 422 value_error + ctx.reason=future_time
      if (
        items.some(
          (x) =>
            (x?.type ?? x?.code) === 'value_error' &&
            (x as { ctx?: { reason?: unknown } })?.ctx?.reason === 'future_time'
        )
      )
        return t('mes.reticle.err.futureTime')
      if (items.some((x) => (x?.type ?? x?.code) === 'idempotency_key_reused'))
        return t('mes.reticle.err.keyReused')
      if (
        items.some(
          (x) =>
            (x?.type ?? x?.code) === 'missing' &&
            x?.loc?.[0] === 'header' &&
            x?.loc?.[1] === 'Idempotency-Key'
        )
      )
        return t('mes.reticle.err.keyMissing')
      const mp = d.find(
        (x: { ctx?: { max_places?: unknown } }) => x?.ctx?.max_places != null
      ) as { ctx: { max_places: unknown } } | undefined
      if (mp) return t('mes.reticle.err.maxPlaces', { max: mp.ctx.max_places })
    }
    const code =
      d && typeof d === 'object' && !Array.isArray(d)
        ? (d as { code?: unknown }).code
        : undefined
    // D82 补充三 / 386c4e0：time_out_of_order 的 latest_event_at 在 detail 顶层
    if (code === 'time_out_of_order') {
      const at = latestEventAt(err)
      // QA P3：用顶层 field 指明是哪个时间字段（如 incident 的 occurred_at 早于上机时间）
      const f = (d as { field?: unknown }).field
      const fk = `mes.reticle.timeField.${String(f)}`
      if (at && typeof f === 'string' && i18n.exists(fk))
        return t('mes.reticle.err.timeOutOfOrderField', {
          field: t(fk),
          at: fmtDateTime(at),
        })
      if (at)
        return t('mes.reticle.err.timeOutOfOrderAt', { at: fmtDateTime(at) })
    }
    // D87：available 直接出检验结果 → 409 invalid_transition（有意设计），提示先开始检验
    if (
      code === 'invalid_transition' &&
      action === 'inspection' &&
      (d as { status_code?: unknown }).status_code === 'available'
    )
      return t('mes.reticle.inspectStartFirst')
    // D57 对象格式 {code:'idempotency_key_reused', message}（D80 补充二）
    if (code === 'idempotency_key_reused') return t('mes.reticle.err.keyReused')
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
  // 判断用十进制比较；比例只用于进度条显示
  if (r.max_shots == null || compareDecimal(r.max_shots, 0) !== 1) return null
  return Number(r.shot_count) / Number(r.max_shots)
}

/** 动作 / 履历 action 枚举（下划线或连字符）→ 三语名称。 */
export function actionLabel(a: string) {
  if (a === 'system') return t('mes.reticle.system')
  const k = a.replace(/_/g, '-')
  return t(`mes.reticle.action.${k}`, { defaultValue: a })
}

/**
 * 寿命等级（P3-F3，黄/红同 FE-F8-2 与后端 life_state，D54-5）：
 * 已用 >= 上限 → over（红，进站 409 不可放行）；上限 × warn_ratio（缺省 0.9）<= 已用 → warn（黄）。
 * 后端给了 life_state 以后端为准；没有上限为 null。全程定点字符串比较（D76）。
 */
export function reticleLifeLevel(
  r: Pick<Reticle, 'shot_count' | 'max_shots' | 'warn_ratio' | 'life_state'>
): ToolLifeLevel | null {
  if (r.max_shots == null || r.max_shots === '') return null
  if (r.life_state === 'reached') return 'over'
  if (r.life_state === 'warning') return 'warn'
  if (r.life_state === 'ok') return 'ok'
  return toolLifeLevel(r.shot_count, r.max_shots, reticleWarnRatio(r))
}

/** 预警比例：warn_ratio（0 < r <= 1）否则 0.9（后端 DEFAULT_WARN）。 */
export const reticleWarnRatio = (r: Pick<Reticle, 'warn_ratio'>) =>
  warnRatio({ warn_ratio: r.warn_ratio })

/** D87：是否待检验——不读 inspection_pending，用 status + inspection_required（报废除外）。 */
export const inspectionPending = (
  r: Pick<Reticle, 'status_code' | 'inspection_required'>
) => r.inspection_required && r.status_code !== 'scrapped'

/** 单个动作的禁用提示：报废终态；D87 available 时出检验结果要先开始检验。 */
export function actionHint(
  r: Pick<Reticle, 'status_code'>,
  a: ReticleAction
): string | undefined {
  const h = disabledHint(r)
  if (h) return h
  if (a === 'inspection' && r.status_code === 'available')
    return t('mes.reticle.inspectStartFirst')
  return undefined
}
