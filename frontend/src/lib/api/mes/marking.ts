/**
 * 打标接口（P3-B1~B3，契约见 architect/design/p3-tasks.md 与 frontend/docs/p3-marking.md）。
 * 后端 B1~B3 未就绪前默认走前端 mock（`VITE_MARKING_MOCK=0` 时改走真实接口）。
 * 请求体一律经 MARKING_BODY 白名单挑选；未定的字段名见文档「待确认」。
 * 按 D78（回应设备集成预审 eap/p3 e462675）：每次打印追加 mes_marking_print（seq 从 1 起），
 * 重打（seq>1）必填 reason_id + comment（≤300）；检验独立成 mes_marking_inspection；
 * 手工打印 / 重打 / 检验必须带 Idempotency-Key（D57）；报废对象 409 invalid_transition；source=manual/eap/simulator。
 * D79：主记录 POST /mes/marking，打印（含首打）POST /mes/marking/{id}/prints；新版本 POST .../{id}/versions；
 * 占位符白名单；自批 422 value_error ctx.reason=self_approval；pass 但读回不一致强制 fail（result_overridden）；
 * 作废后可重新首打（新主记录）；追溯默认不含已作废（include_voided=true 才含）；无 qty。
 */
import { siteDate } from '@/lib/site-tz'
import { http } from '../client'
import { pickBody } from '../request-body'
import { apiError } from './reticle'

/** 模板状态：draft → approved → retired。 */
export const TEMPLATE_STATUSES = ['draft', 'approved', 'retired'] as const
export type TemplateStatus = (typeof TEMPLATE_STATUSES)[number]

/** 日期码 YYWW 的取值日期（开批 / 打标 / 封装完成）。 */
export const DATE_CODE_BASES = [
  'lot_start',
  'marking',
  'assembly_done',
] as const
export type DateCodeBasis = (typeof DATE_CODE_BASES)[number]

/** `mes_marking_template`（status / version / approved_* 只读）。 */
export interface MarkingTemplate {
  id: string
  code: string
  product_id: string
  /** 只读 */
  product_name?: string | null
  customer_id: string
  /** 只读 */
  customer_name?: string | null
  version: number
  status: TemplateStatus
  /** 字符串数组；占位符 `{name}`，只允许 PLACEHOLDERS（D79） */
  lines: string[]
  date_code_basis: DateCodeBasis
  uses_bin: boolean
  created_by: string | null
  created_at: string | null
  approved_by: string | null
  approved_at: string | null
}

/** 新建 / 修改模板的可写字段。 */
export type TemplateInput = Pick<
  MarkingTemplate,
  | 'code'
  | 'product_id'
  | 'customer_id'
  | 'lines'
  | 'date_code_basis'
  | 'uses_bin'
>

/** 打标预览（GET /mes/marking/preview?lot_id=）。 */
export interface MarkingPreview {
  lot_id: string
  lot: string
  bin: string | null
  template_id: string
  template_code: string
  template_version: number
  date_code: string
  /** 预览时尚未发号：null；已有未作废主记录时为原号 */
  trace_code: string | null
  /** 已有未作废主记录时的 id（还没首打则 prints 为空） */
  marking_id?: string | null
  lines: string[]
}

export type InspectResult = 'pass' | 'fail'
export type InspectionStatus = 'pending' | InspectResult

/** 记录来源（同 e10_source）。 */
export const MARKING_SOURCES = ['manual', 'eap', 'simulator'] as const
export type MarkingSource = (typeof MARKING_SOURCES)[number]

/** 打印子记录 `mes_marking_print`（D78 Q1：首打 seq=1，重打 seq>1 必带原因）。 */
export interface MarkingPrint {
  id: string
  seq: number
  reason_id: string | null
  reason_code?: string | null
  comment: string | null
  equipment_id: string | null
  operator: string | null
  printed_at: string
  source: MarkingSource
  external_event_id: string | null
}

/** 检验 `mes_marking_inspection`（D78 Q3/Q4：OCR 读回不一致记 fail，存 expected_code / read_code）。 */
export interface MarkingInspection {
  id: string
  /** 对应的打印子记录（D78 补充二：按打印分组显示） */
  print_id: string
  /** 对应打印的 seq */
  seq: number
  result: InspectResult
  expected_code: string | null
  read_code: string | null
  /** 填了 pass 但读回不一致，系统改记 fail（D79-4）；一直返回，未改写为 false */
  result_overridden: boolean
  comment: string | null
  inspected_by: string | null
  inspected_at: string
  source: MarkingSource
  external_event_id: string | null
}

/** 检验不合格未处理时出站：409 check_blocked，ctx.check=marking_inspection，不可强制放行（D78 Q5）。 */
export const INSPECT_BLOCK_CHECK = 'marking_inspection'
/** 重打原因码类型（reason_code.reason_type）。 */
export const REPRINT_REASON_TYPE = 'marking_reprint'
/** 重打备注长度上限。 */
export const COMMENT_MAX = 300
/** 模板占位符白名单（D79-1）。 */
export const PLACEHOLDERS = [
  'trace_code',
  'date_code',
  'lot_id',
  'product_code',
  'customer_code',
] as const
/** 追溯码规则（D78 Q7：待工艺专家确认，暂按 ≤32、[A-Z0-9-]，可配置）。 */
export const TRACE_CODE_RULE = { maxLength: 32, pattern: /^[A-Z0-9-]+$/ }

/** 「纯空白」判断（D78 补充五）：只认空格、\t、\r、\n、U+3000；不用 trim()（U+FEFF、\x1f 等按格式错误）。 */
export const BLANK_RE = /^[ \t\r\n\u3000]*$/
export const isBlankTraceCode = (v: string) => BLANK_RE.test(v)

/** 打标口径（D79 补充二已定：码点长度、读回码不校验格式、可多次检验；集中在这里便于以后调整）。 */
export interface MarkingPolicy {
  /** 追溯码长度口径：utf16（JS length）或 codepoint（[...s].length，同 Python len） */
  lengthMode: 'utf16' | 'codepoint'
  /** 读回码是否按追溯码规则校验格式；false 时只校验空值，格式不符按不一致强制 fail */
  validateReadCodeFormat: boolean
  /** 同一次打印是否允许多次检验（以最新一次为准） */
  multipleInspections: boolean
}
export const MARKING_POLICY: MarkingPolicy = {
  lengthMode: 'codepoint',
  validateReadCodeFormat: false,
  multipleInspections: true,
}
/** 读回码最大码点数（D79 补充二-3）。 */
export const READ_CODE_MAX = 128

/**
 * 读回码校验（D79 补充三）：缺字段 / null / 空串 / 纯空白 → missing；非字符串 → string_type；
 * 超过 128 码点 → max_length；其余不校验格式、不 trim（U+FEFF、\x1f 按普通字符）。
 */
export function readCodeErrors(
  v: unknown
): ('missing' | 'string_type' | 'max_length')[] {
  if (v == null) return ['missing']
  if (typeof v !== 'string') return ['string_type']
  if (isBlankTraceCode(v)) return ['missing']
  return codeLength(v, 'codepoint') > READ_CODE_MAX ? ['max_length'] : []
}

/**
 * 配置正则白名单（D79 补充二-4，QA N-F1）：只接受单个 ^[...]+$；
 * 类里只能有大写字母、数字和同类升序区间（A-Z、0-9 子区间），- 只能放在类的最后；
 * 不允许 [^…]，不允许任何反斜杠。
 */
export const POSITIVE_CLASS_RE =
  /^\^\[(?:[A-Z](?:-[A-Z])?|[0-9](?:-[0-9])?)+-?\]\+\$$/
export function isAllowedTracePattern(src: string): boolean {
  if (!POSITIVE_CLASS_RE.test(src)) return false
  // 区间须升序（如 Z-A、9-0 不收）
  for (const m of src.slice(2, -3).matchAll(/([A-Z0-9])-([A-Z0-9])/g))
    if (m[1] > m[2]) return false
  return true
}
/** 按口径计算长度。 */
export const codeLength = (
  v: string,
  mode: MarkingPolicy['lengthMode'] = MARKING_POLICY.lengthMode
) => (mode === 'codepoint' ? [...v].length : v.length)

/** pattern 为 null：配置里的正则非法，前端不做格式预校验（以后端为准，QA F6）。 */
export type TraceRule = {
  maxLength: number
  pattern: RegExp | null
  lengthMode?: MarkingPolicy['lengthMode']
}
export type TraceCodeReason = 'missing' | 'max_length' | 'pattern'

/** 追溯码逐条校验：违反几条返回几条（D78 补充三，同后端 422 value_error 逐条 ctx.reason）。 */
export function traceCodeErrors(
  v: string,
  rule: TraceRule = TRACE_CODE_RULE
): TraceCodeReason[] {
  // D78 补充四：空串 / 纯空白只报一条必填；不改写输入（不去空格、不转大写），全串匹配
  if (isBlankTraceCode(v)) return ['missing']
  const out: TraceCodeReason[] = []
  if (codeLength(v, rule.lengthMode) > rule.maxLength) out.push('max_length')
  if (rule.pattern && !rule.pattern.test(v)) out.push('pattern')
  return out
}
/** 第一条错误（兼容单条提示场景）。 */
export const traceCodeError = (v: string, rule: TraceRule = TRACE_CODE_RULE) =>
  traceCodeErrors(v, rule)[0] ?? null

/** GET /mes/marking/config（mes.marking:exec）。 */
export interface MarkingConfig {
  trace_code_max_length: number
  trace_code_pattern: string
}
export const DEFAULT_MARKING_CONFIG: MarkingConfig = {
  trace_code_max_length: 32,
  trace_code_pattern: '^[A-Z0-9-]+$',
}
/** 配置转校验规则：长度缺失用默认；正则非法时 pattern=null（不预校验格式，页面提示以后端为准，QA F6）。 */
export function ruleFromConfig(
  c: Partial<MarkingConfig> | null | undefined
): TraceRule {
  const n = Number(c?.trace_code_max_length)
  let pattern: RegExp | null = TRACE_CODE_RULE.pattern
  if (c?.trace_code_pattern) {
    try {
      pattern = isAllowedTracePattern(c.trace_code_pattern)
        ? new RegExp(c.trace_code_pattern)
        : null
    } catch {
      pattern = null
    }
  }
  return {
    maxLength: Number.isInteger(n) && n > 0 ? n : TRACE_CODE_RULE.maxLength,
    pattern,
  }
}

/** mock 的 GET /mes/marking/config（测试可用 setMarkingMockConfig 改）。 */
let mockConfig: MarkingConfig = { ...DEFAULT_MARKING_CONFIG }
/** 测试用：设置 mock 的打标配置；传 null 恢复默认。 */
export function setMarkingMockConfig(c: Partial<MarkingConfig> | null) {
  mockConfig = { ...DEFAULT_MARKING_CONFIG, ...(c ?? {}) }
}

/**
 * 追溯码 422（D79 补充四）：每条违反规则一条 value_error。
 * 超长 ctx={reason:'max_length', max_length:N}（N 取 config）；
 * 格式 ctx={reason:'pattern', pattern:<config 原样正则>}。
 */
function traceCode422(loc: string, v: string) {
  const cfg = mockConfig
  const rule = ruleFromConfig(cfg)
  // 后端按 config 原样正则校验；前端白名单不收的正则这里也照样编译（编译失败则不校验格式）
  let re: RegExp | null
  try {
    re = new RegExp(cfg.trace_code_pattern)
  } catch {
    re = null
  }
  const bad = traceCodeErrors(v, { ...rule, pattern: re })
  if (!bad.length) return null
  return apiError(
    422,
    bad.map((reason) => ({
      loc: ['body', loc],
      type: reason === 'missing' ? 'missing' : 'value_error',
      code: reason === 'missing' ? 'missing' : 'value_error',
      msg: `${loc}: ${reason}`,
      ctx:
        reason === 'missing'
          ? undefined
          : reason === 'max_length'
            ? { reason, max_length: rule.maxLength }
            : { reason, pattern: cfg.trace_code_pattern },
    }))
  )
}

/** 追溯码格式校验。 */
export const isValidTraceCode = (
  v: string,
  rule: { maxLength: number; pattern: RegExp } = TRACE_CODE_RULE
) => traceCodeError(v, rule) === null

/** 有工步信息且批次已离开打标工步（QA N-F3）；无工步信息时视为未离开，由后端 409 兜底。 */
export const hasLeftMarkingStep = (r: Pick<MarkingRecord, 'at_marking_step'>) =>
  r.at_marking_step === false

/** 检验按钮可用：有打印、未锁定、未离开打标工步；不允许多次检验时只在 pending 可用。 */
export const canInspect = (
  r: Pick<
    MarkingRecord,
    | 'prints'
    | 'latest_inspection_status'
    | 'voided'
    | 'scrapped'
    | 'at_marking_step'
  >,
  policy: MarkingPolicy = MARKING_POLICY
) =>
  !isLocked(r) &&
  !hasLeftMarkingStep(r) &&
  r.prints.length > 0 &&
  (policy.multipleInspections || r.latest_inspection_status === 'pending')

/** 重打按钮可用：已有首打且未锁定（QA F5：决策未限制只能对 fail 重打）。 */
export const canReprint = (
  r: Pick<MarkingRecord, 'prints' | 'voided' | 'scrapped'>
) => !isLocked(r) && r.prints.length > 0

/** 作废 / 批次报废后禁用打印、检验、作废。 */
export const isLocked = (r: Pick<MarkingRecord, 'voided' | 'scrapped'>) =>
  !!r.voided || !!r.scrapped

/** `mes_marking_record`（主记录）。 */
export interface MarkingRecord {
  id: string
  lot_id: string
  lot: string
  template_id: string
  template_code: string
  template_version: number
  content: string[]
  trace_code: string
  /** 日期码 YYWW（站点日期，D75） */
  date_code: string
  equipment_id: string | null
  equipment: string | null
  operator: string | null
  /** 首打时间，之后不变（D79 补充二-6）；未首打为 null */
  marked_at: string | null
  /** 只读：批次是否仍在打标工步；缺省表示无工步信息 */
  at_marking_step?: boolean
  /** 只读：最近一次打印时间 */
  last_printed_at: string | null
  /** 只读：最近一次打印的检验状态；拦出站直接看它，重打后回到 pending（D78 补充二） */
  /** D79 补充六：还没首打时为 null（不是 pending） */
  latest_inspection_status: InspectionStatus | null
  /** 已报废（批次或记录）：后续操作 409 invalid_transition */
  scrapped?: boolean
  /** 已作废（不可恢复） */
  voided?: boolean
  voided_at?: string | null
  voided_by?: string | null
  void_reason_id?: string | null
  void_comment?: string | null
  /** 只读派生：prints.length - 1 */
  reprint_count: number
  prints: MarkingPrint[]
  inspections: MarkingInspection[]
  source: MarkingSource
  external_event_id: string | null
}

/** 创建主记录（POST /mes/marking）。 */
export interface CreateInput {
  lot_id: string
  equipment_id?: string | null
}
/** 打印（POST /mes/marking/{id}/prints）：seq 后端分配；seq>1 必填 reason_id + comment。 */
export interface PrintInput {
  equipment_id?: string | null
  reason_id?: string | null
  comment?: string | null
}
export interface InspectInput {
  result: InspectResult
  /** OCR / 人工读回的码（D79 补充三：必填）；与系统号不一致时一律记 fail */
  read_code: string
  comment?: string | null
}

/** 作废（POST /mes/marking/{id}/void）：reason_id（reason_type=marking_void）+ comment 必填。 */
export interface VoidInput {
  reason_id: string
  comment: string
}
/** 作废原因码类型。 */
export const VOID_REASON_TYPE = 'marking_void'

/** 记录列表筛选：lot_id、marked_at 范围（D77 半开区间，调用方经 rangeParam 生成）。 */
export interface RecordQuery {
  lot_id?: string
  marked_at_from?: string
  marked_at_to?: string
}

/** 检验响应（D79-4）。 */
export interface InspectOut {
  record: MarkingRecord
  result: InspectResult
  expected_code: string
  read_code: string | null
  result_overridden: boolean
}

/** kind=trace_code 追溯结果（D79-6）。 */
export interface TraceCodeResult {
  marking_id: string
  lot_id: string
  trace_code: string
  voided: boolean
  prints: {
    print_id: string
    seq: number
    marked_at: string
    latest_inspection_result: InspectionStatus
  }[]
}

/** 请求体白名单。 */
export const MARKING_BODY = {
  template: [
    'code',
    'product_id',
    'customer_id',
    'lines',
    'date_code_basis',
    'uses_bin',
  ],
  create: ['lot_id', 'equipment_id'],
  print: ['equipment_id', 'reason_id', 'comment'],
  inspect: ['result', 'read_code', 'comment'],
  void: ['reason_id', 'comment'],
  /** 模板预览 / 校验（只读）：只留 template_id、lines */
  templateCheck: ['template_id', 'lines'],
} as const

export interface MarkingApi {
  templates: (q?: {
    status?: TemplateStatus | ''
  }) => Promise<MarkingTemplate[]>
  template: (id: string) => Promise<MarkingTemplate>
  /** 模板写接口 key：Idempotency-Key（D81/D82，必填） */
  createTemplate: (
    input: TemplateInput,
    key: string
  ) => Promise<MarkingTemplate>
  updateTemplate: (
    id: string,
    input: Partial<TemplateInput>,
    key: string
  ) => Promise<MarkingTemplate>
  /** 复制最新版本为草稿（D79-1） */
  newVersion: (id: string, key: string) => Promise<MarkingTemplate>
  approve: (id: string, key: string) => Promise<MarkingTemplate>
  retire: (id: string) => Promise<MarkingTemplate>
  /** POST /mes/marking-template/preview（只读，不带 Idempotency-Key） */
  templatePreview: (input: TemplateCheckInput) => Promise<TemplatePreviewOut>
  /** POST /mes/marking-template/validate（只读，不带 Idempotency-Key） */
  templateValidate: (input: TemplateCheckInput) => Promise<TemplateValidateOut>
  preview: (lotId: string) => Promise<MarkingPreview>
  records: (q: RecordQuery) => Promise<MarkingRecord[]>
  /** 单条主记录（出站拦截提示跳转用） */
  record: (id: string) => Promise<MarkingRecord>
  /** key：Idempotency-Key（D57） */
  create: (input: CreateInput, key: string) => Promise<MarkingRecord>
  print: (id: string, input: PrintInput, key: string) => Promise<MarkingRecord>
  inspect: (id: string, input: InspectInput, key: string) => Promise<InspectOut>
  void: (id: string, input: VoidInput, key: string) => Promise<MarkingRecord>
  config: () => Promise<MarkingConfig>
  trace: (code: string, includeVoided?: boolean) => Promise<TraceCodeResult>
}

/** 模板预览 / 校验请求体（模拟器场景用 {template_id}；未保存草稿可直接给 lines）。 */
export interface TemplateCheckInput {
  template_id?: string
  lines?: string[]
}
export interface TemplatePreviewOut {
  template_id: string | null
  lines: string[]
}
export interface TemplateValidateOut {
  valid: boolean
  unknown_placeholders: string[]
}

const idemHeaders = (key?: string) =>
  key ? { headers: { 'Idempotency-Key': key } } : undefined

export const httpMarkingApi: MarkingApi = {
  templates: (q) =>
    http
      .get<{ data: MarkingTemplate[] }>('/mes/marking-template', {
        params: { page_size: 100, ...(q?.status ? { status: q.status } : {}) },
      })
      .then((r) => r.data.data),
  template: (id) =>
    http
      .get<MarkingTemplate>(`/mes/marking-template/${id}`)
      .then((r) => r.data),
  createTemplate: (input, key) =>
    http
      .post<MarkingTemplate>(
        '/mes/marking-template',
        pickBody(input, MARKING_BODY.template),
        idemHeaders(key)
      )
      .then((r) => r.data),
  updateTemplate: (id, input, key) =>
    http
      .patch<MarkingTemplate>(
        `/mes/marking-template/${id}`,
        pickBody(input, MARKING_BODY.template),
        idemHeaders(key)
      )
      .then((r) => r.data),
  newVersion: (id, key) =>
    http
      .post<MarkingTemplate>(
        `/mes/marking-template/${id}/versions`,
        undefined,
        idemHeaders(key)
      )
      .then((r) => r.data),
  approve: (id, key) =>
    http
      .post<MarkingTemplate>(
        `/mes/marking-template/${id}/approve`,
        undefined,
        idemHeaders(key)
      )
      .then((r) => r.data),
  retire: (id) =>
    http
      .post<MarkingTemplate>(`/mes/marking-template/${id}/retire`)
      .then((r) => r.data),
  templatePreview: (input) =>
    http
      .post<TemplatePreviewOut>(
        '/mes/marking-template/preview',
        pickBody(input, MARKING_BODY.templateCheck)
      )
      .then((r) => r.data),
  templateValidate: (input) =>
    http
      .post<TemplateValidateOut>(
        '/mes/marking-template/validate',
        pickBody(input, MARKING_BODY.templateCheck)
      )
      .then((r) => r.data),
  preview: (lotId) =>
    http
      .get<MarkingPreview>('/mes/marking/preview', {
        params: { lot_id: lotId },
      })
      .then((r) => r.data),
  records: (q) =>
    http
      .get<{ data: MarkingRecord[] }>('/mes/marking', {
        params: { page_size: 100, ...q },
      })
      .then((r) => r.data.data),
  record: (id) =>
    http.get<MarkingRecord>(`/mes/marking/${id}`).then((r) => r.data),
  create: (input, key) =>
    http
      .post<MarkingRecord>(
        '/mes/marking',
        pickBody(input, MARKING_BODY.create),
        idemHeaders(key)
      )
      .then((r) => r.data),
  print: (id, input, key) =>
    http
      .post<MarkingRecord>(
        `/mes/marking/${id}/prints`,
        pickBody(input, MARKING_BODY.print),
        idemHeaders(key)
      )
      .then((r) => r.data),
  inspect: (id, input, key) =>
    http
      .post<InspectOut>(
        `/mes/marking/${id}/inspect`,
        pickBody(input, MARKING_BODY.inspect),
        idemHeaders(key)
      )
      .then((r) => r.data),
  void: (id, input, key) =>
    http
      .post<MarkingRecord>(
        `/mes/marking/${id}/void`,
        pickBody(input, MARKING_BODY.void),
        idemHeaders(key)
      )
      .then((r) => r.data),
  config: () =>
    http.get<MarkingConfig>('/mes/marking/config').then((r) => r.data),
  trace: (code, includeVoided) =>
    http
      .get<TraceCodeResult>('/mes/exec/trace', {
        params: {
          kind: 'trace_code',
          code,
          ...(includeVoided ? { include_voided: true } : {}),
        },
      })
      .then((r) => r.data),
}

// ───────────────────────── 规则（页面与 mock 共用） ─────────────────────────

/** 起草人不能审批自己的模板（B1 验收：审批人不能是起草人）。 */
export const isSelfApproval = (
  tpl: Pick<MarkingTemplate, 'created_by'>,
  me: string | null | undefined
) => !!me && !!tpl.created_by && tpl.created_by === me

/** 已批准 / 已退役版本只读。 */
export const isEditable = (tpl: Pick<MarkingTemplate, 'status'>) =>
  tpl.status === 'draft'

/** ISO 周 YYWW（年取 ISO 周所在年的后两位）。 */
export function isoYyww(ymd: string): string {
  const [y, m, d] = ymd.split('-').map(Number)
  const dt = new Date(Date.UTC(y, m - 1, d))
  const day = dt.getUTCDay() || 7
  dt.setUTCDate(dt.getUTCDate() + 4 - day)
  const year = dt.getUTCFullYear()
  const week = Math.ceil(
    ((dt.getTime() - Date.UTC(year, 0, 1)) / 86400000 + 1) / 7
  )
  return `${String(year).slice(-2)}${String(week).padStart(2, '0')}`
}

/** 模板行里用到的白名单以外的占位符（D79-1，前端预校验；后端 422 value_error ctx.reason=unknown_placeholder）。 */
export function unknownPlaceholders(lines: string[]): string[] {
  const bad = new Set<string>()
  for (const l of lines)
    for (const m of l.matchAll(/\{([^{}]*)\}/g))
      if (!(PLACEHOLDERS as readonly string[]).includes(m[1])) bad.add(m[1])
  return [...bad]
}

/** 按模板行替换占位符生成打标内容（未发号时 trace_code 显示占位）。 */
export function renderLines(
  lines: string[],
  v: Record<(typeof PLACEHOLDERS)[number], string | null>
): string[] {
  return lines.map((l) =>
    l.replace(
      /\{(trace_code|date_code|lot_id|product_code|customer_code)\}/g,
      (_, k: (typeof PLACEHOLDERS)[number]) =>
        v[k] ?? (k === 'trace_code' ? '••••' : '')
    )
  )
}

/** 版本对比的一项差异。 */
export interface TemplateDiff {
  field: 'date_code_basis' | 'uses_bin' | 'lines'
  /** 仅 lines：行号（从 1 开始） */
  line?: number
  before: string | null
  after: string | null
}

/** 两个版本逐字段、逐行对比（只比业务字段，不比状态 / 审批信息）。 */
export function diffTemplates(
  a: MarkingTemplate,
  b: MarkingTemplate
): TemplateDiff[] {
  const out: TemplateDiff[] = []
  if (a.date_code_basis !== b.date_code_basis)
    out.push({
      field: 'date_code_basis',
      before: a.date_code_basis,
      after: b.date_code_basis,
    })
  if (a.uses_bin !== b.uses_bin)
    out.push({
      field: 'uses_bin',
      before: String(a.uses_bin),
      after: String(b.uses_bin),
    })
  const n = Math.max(a.lines.length, b.lines.length)
  for (let i = 0; i < n; i++) {
    const x = a.lines[i] ?? null
    const y = b.lines[i] ?? null
    if (x !== y) out.push({ field: 'lines', line: i + 1, before: x, after: y })
  }
  return out
}

/** 同一「产品+客户」的其他版本（版本对比的候选）。 */
export const siblingVersions = (all: MarkingTemplate[], tpl: MarkingTemplate) =>
  all
    .filter(
      (x) =>
        x.id !== tpl.id &&
        x.product_id === tpl.product_id &&
        x.customer_id === tpl.customer_id
    )
    .sort((x, y) => y.version - x.version)

/** 重打原因校验：reason_id、comment 都必填，comment ≤300；返回缺失 / 超长字段。 */
export function reprintErrors(
  input: Pick<PrintInput, 'reason_id' | 'comment'>
): ('reason_id' | 'comment' | 'comment_too_long')[] {
  const out: ('reason_id' | 'comment' | 'comment_too_long')[] = []
  // D78 补充五：纯空白按正则判断，不用 trim；长度按码点（D79 补充二）
  if (input.reason_id == null || isBlankTraceCode(input.reason_id))
    out.push('reason_id')
  if (input.comment == null || isBlankTraceCode(input.comment))
    out.push('comment')
  else if (commentTooLong(input.comment)) out.push('comment_too_long')
  return out
}

/** comment 是否超过 300 码点。 */
export const commentTooLong = (v: string) => [...v].length > COMMENT_MAX

/** 检验最终结果：读回码与系统号不一致时强制 fail（D78 Q3）。 */
export const effectiveResult = (
  input: InspectInput,
  expected: string
): InspectResult =>
  typeof input.read_code === 'string' && input.read_code !== expected
    ? 'fail'
    : input.result

/** 检验履历按打印分组（seq 升序）。 */
export function inspectionsByPrint(
  r: Pick<MarkingRecord, 'prints' | 'inspections'>
) {
  return [...r.prints]
    .sort((a, b) => a.seq - b.seq)
    .map((p) => ({
      print: p,
      inspections: r.inspections.filter((i) => i.print_id === p.id),
    }))
}

/** 最新一条检验（按时间）。 */
export const lastInspection = (r: Pick<MarkingRecord, 'inspections'>) =>
  r.inspections.length ? r.inspections[r.inspections.length - 1] : null

/**
 * 出站拦截判断（D79 补充）：只看未作废主记录（同一批次最多一条）；已作废记录上的 fail 不拦。
 * 产品有已批准模板但没有未作废主记录 → not_marked；最新打印待检 / 不合格 → pending / fail；合格 → null。
 */
export function trackOutBlock(
  records: Pick<MarkingRecord, 'voided' | 'latest_inspection_status'>[],
  hasApprovedTemplate = true
): 'not_marked' | 'pending' | 'fail' | null {
  const live = records.find((r) => !r.voided)
  if (!live) return hasApprovedTemplate ? 'not_marked' : null
  // D79 补充六：未首打（null）按未打标处理
  if (live.latest_inspection_status == null) return 'not_marked'
  return live.latest_inspection_status === 'pass'
    ? null
    : live.latest_inspection_status
}

/** 出站 check_blocked（marking_inspection）的 ctx.reason（D79 补充）。 */
export const MARKING_BLOCK_REASONS = ['not_marked', 'pending', 'fail'] as const
export type MarkingBlockReason = (typeof MARKING_BLOCK_REASONS)[number]

/**
 * mock：出站时的打标拦截（D78 Q5 / D79 补充 5、6 / D82）。不拦返回 null；拦截时返回 409 check_blocked：
 * `ctx.check=marking_inspection`、`overridable=false`、`ctx.reason`，有未作废主记录（含未首打）时带 `marking_id`。
 * results[] 同时带同样的 ctx，供出站面板逐项显示。
 */
export function mockTrackOutMarkingCheck(lotId: string) {
  const lot = LOTS.find((l) => l.id === lotId || l.code === lotId)
  if (!lot) return null
  const hasTpl = store.t.some(
    (y) =>
      y.product_id === lot.product_id &&
      y.customer_id === lot.customer_id &&
      y.status === 'approved'
  )
  if (!hasTpl) return null
  const live = liveRec(lot.id)
  const reason = trackOutBlock(live ? [live] : [], true)
  if (!reason) return null
  const ctx: Record<string, unknown> = { check: INSPECT_BLOCK_CHECK, reason }
  if (live) {
    ctx.marking_id = live.id
    // 后端答复（P3 Q4）：未首打时 trace_code 为 null
    ctx.trace_code = live.prints.length ? live.trace_code : null
  }
  return apiError(409, {
    code: 'check_blocked',
    message: `marking inspection ${reason}`,
    overridable: false,
    ctx,
    results: [
      {
        check_type: INSPECT_BLOCK_CHECK,
        result: 'block',
        overridable: false,
        message: `marking inspection ${reason}`,
        ctx,
      },
    ],
  })
}

/** 请求体签名（同 key 不同内容 → 422 idempotency_key_reused）。 */
export const markingSignature = (op: string, body: object) =>
  `${op}:${JSON.stringify(body, Object.keys(body).sort())}`

// ───────────────────────── mock ─────────────────────────

interface MockLot {
  id: string
  code: string
  product_id: string
  product_code: string
  customer_id: string
  customer_code: string
  bin: string | null
  started_at: string
  scrapped?: boolean
  /** 已离开打标工步（之后检验 409） */
  left_step?: boolean
}

const LOTS: MockLot[] = [
  {
    id: 'lot1',
    code: 'LOT-A001',
    product_id: 'p1',
    product_code: 'FS3201',
    customer_id: 'c1',
    customer_code: 'ACME',
    bin: null,
    started_at: '2026-10-05T02:00:00Z',
  },
  {
    id: 'lot2',
    code: 'LOT-B001-001',
    product_id: 'p2',
    product_code: 'FS0802',
    customer_id: 'c2',
    customer_code: 'GLOBEX',
    bin: 'B1',
    started_at: '2026-10-06T02:00:00Z',
  },
  {
    id: 'lot3',
    code: 'LOT-C001',
    product_id: 'p3',
    product_code: 'FS9000',
    customer_id: 'c1',
    customer_code: 'ACME',
    bin: null,
    started_at: '2026-10-07T02:00:00Z',
  },
  {
    id: 'lot4',
    code: 'LOT-A002',
    product_id: 'p1',
    product_code: 'FS3201',
    customer_id: 'c1',
    customer_code: 'ACME',
    bin: null,
    started_at: '2026-10-05T02:00:00Z',
    scrapped: true,
  },
]
const NAMES: Record<string, string> = {
  p1: 'QFN32-A',
  p2: 'SOP8-B',
  p3: 'BGA-C',
  c1: 'ACME',
  c2: 'Globex',
}

const tplSeed = (): MarkingTemplate[] => [
  {
    id: 't1',
    code: 'MK-QFN32-ACME',
    product_id: 'p1',
    product_name: 'QFN32-A',
    customer_id: 'c1',
    customer_name: 'ACME',
    version: 1,
    status: 'retired',
    lines: ['{product_code}', '{date_code}'],
    date_code_basis: 'lot_start',
    uses_bin: false,
    created_by: 'eng1',
    created_at: '2026-09-01T01:00:00Z',
    approved_by: 'qa1',
    approved_at: '2026-09-02T01:00:00Z',
  },
  {
    id: 't2',
    code: 'MK-QFN32-ACME',
    product_id: 'p1',
    product_name: 'QFN32-A',
    customer_id: 'c1',
    customer_name: 'ACME',
    version: 2,
    status: 'approved',
    lines: ['{product_code}', '{date_code} {trace_code}'],
    date_code_basis: 'marking',
    uses_bin: false,
    created_by: 'eng1',
    created_at: '2026-10-01T01:00:00Z',
    approved_by: 'qa1',
    approved_at: '2026-10-02T01:00:00Z',
  },
  {
    id: 't3',
    code: 'MK-SOP8-GLOBEX',
    product_id: 'p2',
    product_name: 'SOP8-B',
    customer_id: 'c2',
    customer_name: 'Globex',
    version: 1,
    status: 'draft',
    lines: ['{product_code}', '{date_code}{trace_code}'],
    date_code_basis: 'assembly_done',
    uses_bin: true,
    created_by: 'admin',
    created_at: '2026-10-14T01:00:00Z',
    approved_by: null,
    approved_at: null,
  },
]

interface Store {
  t: MarkingTemplate[]
  rec: MarkingRecord[]
  seq: Record<string, number>
  n: number
}
const seed = (): Store => ({ t: tplSeed(), rec: [], seq: {}, n: 0 })
let store = seed()
const idem = new Map<string, { sig: string; out: unknown }>()
let mockUser = 'admin'
let mockNow: () => Date = () => new Date()

/** 测试用：重置 mock 数据。 */
export function resetMarkingMock() {
  store = seed()
  setMarkingMockConfig(null)
  for (const l of LOTS) delete l.left_step
  idem.clear()
  mockUser = 'admin'
  mockNow = () => new Date()
}
/** mock 的当前用户（真实接口由会话决定；页面用 /auth/me 的 username 同步）。 */
export const setMarkingMockUser = (u: string) => {
  mockUser = u
}
/** 测试用：固定 mock 时钟。 */
export const setMarkingMockNow = (f: () => Date) => {
  mockNow = f
}

const later = <T>(f: () => T): Promise<T> =>
  new Promise((res, rej) =>
    setTimeout(() => {
      try {
        res(structuredClone(f()))
      } catch (e) {
        rej(e)
      }
    }, 0)
  )
const err409 = (code: string, message: string, extra: object = {}) =>
  apiError(409, { code, message, ...extra })
const err422 = (
  loc: string,
  type: string,
  msg: string,
  ctx?: Record<string, unknown>
) => apiError(422, [{ loc: ['body', loc], type, code: type, msg, ctx }])
/** D79 补充四：超长 value_error ctx={reason:max_length, max_length:N}。 */
const commentLongErr = () =>
  err422('comment', 'value_error', 'comment: at most 300 characters', {
    reason: 'max_length',
    max_length: COMMENT_MAX,
  })
const scrappedErr = () =>
  err409('invalid_transition', 'lot or marking record is scrapped or voided')

/**
 * D57：缺 key 422 missing（header）；同 key 同内容返回首次结果；不同内容 422 idempotency_key_reused。
 * N-E2：顺序与后端一致 —— 缺 key 422 → 请求体 422（pre）→ 幂等重放 → 状态 / 业务 409（f）。
 */
function withIdem<T>(
  key: string | undefined,
  sig: string,
  f: () => T,
  pre?: () => void
): T {
  if (!key)
    throw apiError(422, [
      {
        loc: ['header', 'Idempotency-Key'],
        type: 'missing',
        code: 'missing',
        msg: 'Idempotency-Key: field required',
      },
    ])
  pre?.()
  const hit = idem.get(key)
  if (hit) {
    // D57 / D80 补充二：本期维持对象格式 {code, message}
    if (hit.sig !== sig)
      throw apiError(422, {
        code: 'idempotency_key_reused',
        message: 'Idempotency-Key reused with a different body',
      })
    return structuredClone(hit.out) as T
  }
  const out = f()
  idem.set(key, { sig, out: structuredClone(out) })
  return out
}

const findTpl = (id: string) => {
  const x = store.t.find((y) => y.id === id)
  if (!x) throw apiError(404, 'not found')
  return x
}
const findLot = (id: string) => {
  const x = LOTS.find((l) => l.id === id || l.code === id)
  if (!x) throw apiError(404, 'not found')
  return x
}
const findRec = (id: string) => {
  const r = store.rec.find((x) => x.id === id)
  if (!r) throw apiError(404, 'not found')
  return r
}
const lotOf = (r: MarkingRecord) => LOTS.find((l) => l.id === r.lot_id)
const activeTpl = (lot: MockLot) => {
  const x = store.t.find(
    (y) =>
      y.product_id === lot.product_id &&
      y.customer_id === lot.customer_id &&
      y.status === 'approved'
  )
  if (!x)
    throw err409('marking_template_missing', 'no approved marking template')
  return x
}
/** 当前未作废主记录（同一批次最多一条，D79-5）。 */
const liveRec = (lotId: string) =>
  store.rec.find((r) => r.lot_id === lotId && !r.voided)
/** 日期码取值日期（站点时区，D75）。 */
const basisDate = (tpl: MarkingTemplate, lot: MockLot) =>
  siteDate(tpl.date_code_basis === 'lot_start' ? lot.started_at : mockNow())
const values = (lot: MockLot, yyww: string, trace: string | null) => ({
  trace_code: trace,
  date_code: yyww,
  lot_id: lot.code,
  product_code: lot.product_code,
  customer_code: lot.customer_code,
})

function validateTemplate(input: Partial<TemplateInput>, create: boolean) {
  for (const k of ['code', 'product_id', 'customer_id'] as const)
    if (create && !input[k]?.toString().trim())
      throw err422(k, 'missing', `${k}: field required`)
  if (input.lines !== undefined) {
    if (!input.lines.some((l) => !isBlankTraceCode(l)))
      throw err422('lines', 'missing', 'lines: at least one line')
    const bad = unknownPlaceholders(input.lines)
    if (bad.length)
      throw apiError(
        422,
        bad.map((name) => ({
          loc: ['body', 'lines'],
          type: 'value_error',
          code: 'value_error',
          msg: `lines: unknown placeholder {${name}}`,
          ctx: { reason: 'unknown_placeholder', placeholder: name },
        }))
      )
  }
}

function mockCreate(input: TemplateInput): MarkingTemplate {
  validateTemplate(input, true)
  const same = store.t.filter(
    (y) =>
      y.product_id === input.product_id && y.customer_id === input.customer_id
  )
  if (same.some((y) => y.status === 'draft'))
    throw err409('draft_exists', 'a draft already exists')
  const tpl = {
    ...pickBody(input, MARKING_BODY.template),
    // QA F4：不静默丢弃空行，原样保存（后端口径待对齐）
    lines: [...input.lines],
    id: `t${store.t.length + 1}-${++store.n}`,
    product_name: NAMES[input.product_id] ?? null,
    customer_name: NAMES[input.customer_id] ?? null,
    version: Math.max(0, ...same.map((y) => y.version)) + 1,
    status: 'draft',
    created_by: mockUser,
    created_at: mockNow().toISOString(),
    approved_by: null,
    approved_at: null,
  } as MarkingTemplate
  store.t.push(tpl)
  return tpl
}

/** D79-1：复制同「产品+客户」的最新版本为草稿，版本号递增。 */
function mockNewVersion(id: string): MarkingTemplate {
  const base = findTpl(id)
  const same = store.t.filter(
    (y) =>
      y.product_id === base.product_id && y.customer_id === base.customer_id
  )
  if (same.some((y) => y.status === 'draft'))
    throw err409('draft_exists', 'a draft already exists')
  const latest = same.reduce((a, b) => (b.version > a.version ? b : a))
  const tpl: MarkingTemplate = {
    ...structuredClone(latest),
    id: `t${store.t.length + 1}-${++store.n}`,
    version: latest.version + 1,
    status: 'draft',
    created_by: mockUser,
    created_at: mockNow().toISOString(),
    approved_by: null,
    approved_at: null,
  }
  store.t.push(tpl)
  return tpl
}

function mockUpdate(id: string, input: Partial<TemplateInput>) {
  // D81：请求体 422 → 404 → 409 template_readonly
  validateTemplate(input, false)
  const tpl = findTpl(id)
  if (!isEditable(tpl))
    throw err409('template_readonly', 'approved template is read-only')
  Object.assign(tpl, pickBody(input, MARKING_BODY.template))
  return tpl
}

function mockApprove(id: string) {
  const tpl = findTpl(id)
  // D79-2：自批 422 value_error ctx.reason=self_approval（同 D74）。
  // 需查到记录才能判断的 422 排在 404 之后、409 之前：非草稿自批也先返回 self_approval
  if (isSelfApproval(tpl, mockUser))
    throw err422(
      'approved_by',
      'value_error',
      'approver cannot be the drafter',
      {
        reason: 'self_approval',
      }
    )
  if (tpl.status !== 'draft')
    throw err409('invalid_transition', 'only draft can be approved')
  for (const y of store.t)
    if (
      y.status === 'approved' &&
      y.product_id === tpl.product_id &&
      y.customer_id === tpl.customer_id
    )
      y.status = 'retired'
  tpl.status = 'approved'
  tpl.approved_by = mockUser
  tpl.approved_at = mockNow().toISOString()
  return tpl
}

function mockRetire(id: string) {
  const tpl = findTpl(id)
  if (tpl.status !== 'approved')
    throw err409('invalid_transition', 'only approved can be retired')
  tpl.status = 'retired'
  return tpl
}

/** template_id 与 lines 二选一：都传 / 都不传 422 value_error（请求体 422 先于 404）。 */
const checkLines = (input: TemplateCheckInput) => {
  const hasId = input.template_id != null
  const hasLines = input.lines != null
  if (hasId === hasLines)
    throw err422(
      'template_id',
      'value_error',
      'exactly one of template_id or lines is required',
      { reason: 'exactly_one_of', fields: ['template_id', 'lines'] }
    )
  return hasId ? findTpl(input.template_id!).lines : input.lines!
}

/** 模板预览（只读）：用示例值渲染。 */
function mockTplPreview(input: TemplateCheckInput): TemplatePreviewOut {
  return {
    lines: renderLines(checkLines(input), {
      trace_code: '26420001',
      date_code: '2642',
      lot_id: 'LOT-SAMPLE',
      product_code: 'PRODUCT',
      customer_code: 'CUSTOMER',
    }),
    // 传 lines 时 template_id 为 null
    template_id: input.template_id ?? null,
  }
}

/** 模板校验（只读）：白名单外占位符。 */
function mockTplValidate(input: TemplateCheckInput): TemplateValidateOut {
  const bad = unknownPlaceholders(checkLines(input))
  return { valid: bad.length === 0, unknown_placeholders: bad }
}

function mockPreview(lotId: string): MarkingPreview {
  const lot = findLot(lotId)
  const tpl = activeTpl(lot)
  const live = liveRec(lot.id)
  const yyww = live?.date_code ?? isoYyww(basisDate(tpl, lot))
  return {
    lot_id: lot.id,
    lot: lot.code,
    bin: lot.bin,
    template_id: live?.template_id ?? tpl.id,
    template_code: live?.template_code ?? tpl.code,
    template_version: live?.template_version ?? tpl.version,
    date_code: yyww,
    trace_code: live?.trace_code ?? null,
    marking_id: live?.id ?? null,
    lines: live
      ? live.content
      : renderLines(tpl.lines, values(lot, yyww, null)),
  }
}

/** D79-3：创建主记录（发号），不打印。同一批次已有未作废主记录 409 already_marked。 */
function mockCreateRec(input: CreateInput): MarkingRecord {
  const lot = findLot(input.lot_id)
  if (lot.scrapped) throw scrappedErr()
  if (liveRec(lot.id))
    throw err409('already_marked', 'lot already has a live marking record')
  const tpl = activeTpl(lot)
  const yyww = isoYyww(basisDate(tpl, lot))
  const key = `${lot.customer_id}|${lot.product_id}|${yyww}`
  const no = (store.seq[key] = (store.seq[key] ?? 0) + 1)
  const trace = `${yyww}${String(no).padStart(4, '0')}`
  const rec: MarkingRecord = {
    id: `m${++store.n}`,
    lot_id: lot.id,
    lot: lot.code,
    template_id: tpl.id,
    template_code: tpl.code,
    template_version: tpl.version,
    content: renderLines(tpl.lines, values(lot, yyww, trace)),
    trace_code: trace,
    date_code: yyww,
    equipment_id: input.equipment_id ?? null,
    equipment: input.equipment_id ?? null,
    operator: mockUser,
    marked_at: null,
    last_printed_at: null,
    at_marking_step: true,
    latest_inspection_status: null,
    reprint_count: 0,
    prints: [],
    inspections: [],
    source: 'manual',
    external_event_id: null,
  }
  store.rec.push(rec)
  return rec
}

/** 打印请求体 422（与 seq 无关的部分）：comment 超长。 */
function printBody(input: PrintInput) {
  if (typeof input.comment === 'string' && commentTooLong(input.comment))
    throw commentLongErr()
}

/**
 * D79-3：打印（含首打），seq 后端分配；seq>1 必填 reason_id + comment（D78；D79 补充二 5：不要求上次检验为 fail）。
 * 顺序：404 → 重打缺原因 422 missing（取决于 seq，只能查到主记录后判断）→ 已报废 / 作废 409。
 */
function mockPrint(id: string, input: PrintInput): MarkingRecord {
  const r = findRec(id)
  const seq = r.prints.length + 1
  if (seq > 1) {
    const miss = reprintErrors(input)
    if (miss.includes('reason_id'))
      throw err422('reason_id', 'missing', 'reason_id: field required')
    if (miss.includes('comment'))
      throw err422('comment', 'missing', 'comment: field required')
  }
  if (isLocked(r) || lotOf(r)?.scrapped) throw scrappedErr()
  const at = mockNow().toISOString()
  r.prints.push({
    id: `${r.id}-p${seq}`,
    seq,
    reason_id: seq > 1 ? input.reason_id! : null,
    reason_code: seq > 1 ? input.reason_id : null,
    comment: seq > 1 ? input.comment! : null,
    equipment_id: input.equipment_id || r.equipment_id,
    operator: mockUser,
    printed_at: at,
    source: 'manual',
    external_event_id: null,
  })
  r.reprint_count = r.prints.length - 1
  r.latest_inspection_status = 'pending'
  if (seq === 1) r.marked_at = at
  r.last_printed_at = at
  r.operator = mockUser
  if (input.equipment_id) {
    r.equipment_id = input.equipment_id
    r.equipment = input.equipment_id
  }
  return r
}

/** 检验请求体 422（N-E2：先于幂等重放和 409 状态校验）。 */
function inspectBody(input: InspectInput) {
  if (input.result !== 'pass' && input.result !== 'fail')
    throw err422('result', 'enum', 'result: pass or fail')
  // 后端补充确认：comment ≤300，超长 value_error ctx={reason:max_length, max_length:300}
  if (typeof input.comment === 'string' && commentTooLong(input.comment))
    throw commentLongErr()
  {
    // D79 补充三：校验不过不入库、不强制 fail
    const e = readCodeErrors(input.read_code)
    if (e[0] === 'missing')
      throw err422('read_code', 'missing', 'read_code: field required')
    if (e[0] === 'string_type')
      throw err422('read_code', 'string_type', 'read_code: must be a string')
    if (MARKING_POLICY.validateReadCodeFormat) {
      const bad = traceCode422('read_code', input.read_code)
      if (bad) throw bad
    } else {
      if (e[0] === 'max_length')
        throw err422('read_code', 'value_error', 'read_code: too long', {
          reason: 'max_length',
          max_length: READ_CODE_MAX,
        })
    }
  }
}

function mockInspect(id: string, input: InspectInput): InspectOut {
  const r = findRec(id)
  if (isLocked(r) || lotOf(r)?.scrapped) throw scrappedErr()
  inspectBody(input)
  if (!r.prints.length)
    throw err409('invalid_transition', 'nothing printed yet')
  // D79 补充二-1：同一次打印可多次检验，以最新一次为准；批次离开打标工步后 409
  if (lotOf(r)?.left_step)
    throw err409('invalid_transition', 'lot has left the marking step')
  const print = r.prints[r.prints.length - 1]
  const result = effectiveResult(input, r.trace_code)
  const overridden = result !== input.result
  r.inspections.push({
    id: `${r.id}-i${r.inspections.length + 1}`,
    print_id: print.id,
    seq: print.seq,
    result,
    expected_code: r.trace_code,
    read_code: input.read_code ?? null,
    result_overridden: overridden,
    comment: input.comment ?? null,
    inspected_by: mockUser,
    inspected_at: mockNow().toISOString(),
    source: 'manual',
    external_event_id: null,
  })
  r.latest_inspection_status = result
  return {
    record: r,
    result,
    expected_code: r.trace_code,
    read_code: input.read_code ?? null,
    result_overridden: overridden,
  }
}

/** 作废请求体 422（N-E2）。 */
function voidBody(input: VoidInput) {
  const miss = reprintErrors(input)
  if (miss.includes('reason_id'))
    throw err422('reason_id', 'missing', 'reason_id: field required')
  if (miss.includes('comment'))
    throw err422('comment', 'missing', 'comment: field required')
  if (miss.includes('comment_too_long')) throw commentLongErr()
}

function mockVoid(id: string, input: VoidInput) {
  const r = findRec(id)
  if (isLocked(r) || lotOf(r)?.scrapped) throw scrappedErr()
  r.voided = true
  r.voided_at = mockNow().toISOString()
  r.voided_by = mockUser
  r.void_reason_id = input.reason_id
  r.void_comment = input.comment
  return r
}

/**
 * D77：marked_at 范围半开区间 [from, to)；D77 补充一：from 晚于 to → 422 value_error range_inverted；
 * D79 补充六：按 marked_at 筛选时排除 marked_at 为 null（未首打）的行。
 */
function mockRecords(q: RecordQuery) {
  const t = (s: string | null) => (s ? new Date(s).getTime() : NaN)
  if (
    q.marked_at_from &&
    q.marked_at_to &&
    t(q.marked_at_from) > t(q.marked_at_to)
  )
    throw apiError(422, [
      {
        loc: ['query', 'marked_at_from'],
        type: 'value_error',
        code: 'value_error',
        msg: 'marked_at: from is after to',
        ctx: { reason: 'range_inverted' },
      },
    ])
  const ranged = !!(q.marked_at_from || q.marked_at_to)
  return store.rec
    .filter((r) => !ranged || r.marked_at != null)
    .filter((r) => !q.lot_id || r.lot_id === q.lot_id || r.lot === q.lot_id)
    .filter((r) => !q.marked_at_from || t(r.marked_at) >= t(q.marked_at_from))
    .filter((r) => !q.marked_at_to || t(r.marked_at) < t(q.marked_at_to))
    .sort((a, b) => (b.marked_at ?? '~').localeCompare(a.marked_at ?? '~'))
}

/** D79-6：kind=trace_code；默认不含已作废，include_voided=true 才含。格式不符逐条 422。 */
function mockTrace(code: string, includeVoided?: boolean): TraceCodeResult {
  const bad = traceCode422('code', code)
  if (bad) throw bad
  const r = store.rec.find(
    (x) => x.trace_code === code && (includeVoided || !x.voided)
  )
  if (!r) throw apiError(404, 'not found')
  return {
    marking_id: r.id,
    lot_id: r.lot_id,
    trace_code: r.trace_code,
    voided: !!r.voided,
    prints: r.prints.map((p) => {
      const insp = r.inspections.filter((i) => i.print_id === p.id)
      return {
        print_id: p.id,
        seq: p.seq,
        marked_at: p.printed_at,
        latest_inspection_result: insp.length
          ? insp[insp.length - 1].result
          : 'pending',
      }
    }),
  }
}

const sig = (op: string, body: object) => markingSignature(op, body)

/** 前端 mock 实现（同形数据与错误码）。 */
export const mockMarkingApi: MarkingApi = {
  templates: (q) =>
    later(() => store.t.filter((x) => !q?.status || x.status === q.status)),
  template: (id) => later(() => findTpl(id)),
  // D81/D82：模板写接口 Idempotency-Key 必填；顺序 缺 key 422 → 请求体 422 → 重放 → 404 → 422 → 409
  createTemplate: (input, key) =>
    later(() =>
      withIdem(
        key,
        markingSignature('tpl-create', input),
        () => mockCreate(input),
        () => validateTemplate(input, true)
      )
    ),
  updateTemplate: (id, input, key) =>
    later(() =>
      withIdem(
        key,
        markingSignature(`tpl-update:${id}`, input),
        () => mockUpdate(id, input),
        () => validateTemplate(input, false)
      )
    ),
  newVersion: (id, key) =>
    later(() =>
      withIdem(key, markingSignature(`tpl-version:${id}`, {}), () =>
        mockNewVersion(id)
      )
    ),
  approve: (id, key) =>
    later(() =>
      withIdem(key, markingSignature(`tpl-approve:${id}`, {}), () =>
        mockApprove(id)
      )
    ),
  retire: (id) => later(() => mockRetire(id)),
  templatePreview: (input) =>
    later(() => mockTplPreview(pickBody(input, MARKING_BODY.templateCheck))),
  templateValidate: (input) =>
    later(() => mockTplValidate(pickBody(input, MARKING_BODY.templateCheck))),
  preview: (lotId) => later(() => mockPreview(lotId)),
  records: (q) => later(() => mockRecords(q)),
  record: (id) => later(() => findRec(id)),
  create: (input, key) =>
    later(() =>
      withIdem(key, sig('create', pickBody(input, MARKING_BODY.create)), () =>
        mockCreateRec(input)
      )
    ),
  print: (id, input, key) =>
    later(() =>
      withIdem(
        key,
        sig(`print:${id}`, pickBody(input, MARKING_BODY.print)),
        () => mockPrint(id, input),
        () => printBody(input)
      )
    ),
  inspect: (id, input, key) =>
    later(() =>
      withIdem(
        key,
        sig(`inspect:${id}`, pickBody(input, MARKING_BODY.inspect)),
        () => mockInspect(id, input),
        () => inspectBody(input)
      )
    ),
  void: (id, input, key) =>
    later(() =>
      withIdem(
        key,
        sig(`void:${id}`, pickBody(input, MARKING_BODY.void)),
        () => mockVoid(id, input),
        () => voidBody(input)
      )
    ),
  config: () => later(() => ({ ...mockConfig })),
  trace: (code, includeVoided) => later(() => mockTrace(code, includeVoided)),
}

/**
 * mock：EAP 回报打印结果（D78 Q3）。号与系统发号不一致 409 trace_code_mismatch（ctx.expected / actual）；
 * 已报废 / 作废 409 invalid_transition。
 */
export function mockEapPrintReport(
  lotId: string,
  report: {
    trace_code: string
    external_event_id: string
    source?: MarkingSource
  }
) {
  return later(() => {
    const lot = findLot(lotId)
    if (lot.scrapped) throw scrappedErr()
    // D79 补充：找不到未作废主记录 409 no_active_marking
    const r = liveRec(lot.id)
    if (!r) throw err409('no_active_marking', 'no live marking record for lot')
    const bad = traceCode422('trace_code', report.trace_code)
    if (bad) throw bad
    if (report.trace_code !== r.trace_code)
      throw err409('trace_code_mismatch', 'reported trace code differs', {
        ctx: { expected: r.trace_code, actual: report.trace_code },
      })
    const src = report.source ?? 'eap'
    const dup = r.prints.some(
      (p) =>
        p.source === src && p.external_event_id === report.external_event_id
    )
    return { record: r, duplicate: dup }
  })
}

/** 测试用：批次离开打标工步。 */
export function markingMockLeaveStep(lotId: string) {
  const l = LOTS.find((x) => x.id === lotId)
  if (l) l.left_step = true
  for (const r of store.rec) if (r.lot_id === lotId) r.at_marking_step = false
}

/** 测试用：把 mock 记录标为已报废。 */
export function scrapMarkingMockRecord(id: string) {
  const r = store.rec.find((x) => x.id === id)
  if (r) r.scrapped = true
}

/** 是否使用 mock（后端 B1~B3 就绪后设 VITE_MARKING_MOCK=0）。 */
export const MARKING_MOCK = import.meta.env.VITE_MARKING_MOCK !== '0'

export const markingApi: MarkingApi = MARKING_MOCK
  ? mockMarkingApi
  : httpMarkingApi
