import type { AxiosError } from 'axios'
import { beforeEach, describe, expect, it } from 'vitest'
import {
  diffTemplates,
  effectiveResult,
  isoYyww,
  isSelfApproval,
  inspectionsByPrint,
  isValidTraceCode,
  traceCodeError,
  MARKING_BODY,
  mockEapPrintReport,
  mockMarkingApi as api,
  renderLines,
  reprintErrors,
  resetMarkingMock,
  scrapMarkingMockRecord,
  setMarkingMockNow,
  setMarkingMockUser,
  siblingVersions,
  tooManyPlaces,
  TRACE_CODE_RULE,
} from './marking'

const detail = async (p: Promise<unknown>) => {
  try {
    await p
  } catch (e) {
    const r = (e as AxiosError).response!
    return { status: r.status, detail: (r.data as { detail: unknown }).detail }
  }
  throw new Error('expected rejection')
}

beforeEach(() => {
  resetMarkingMock()
  // 台北 2026-10-15 01:00（UTC 仍是 10-14）
  setMarkingMockNow(() => new Date('2026-10-14T17:00:00Z'))
})

describe('打标规则', () => {
  it('ISO 周 YYWW', () => {
    expect(isoYyww('2026-10-15')).toBe('2642')
    expect(isoYyww('2027-01-01')).toBe('2653')
    expect(isoYyww('2026-01-01')).toBe('2601')
  })
  it('占位符替换，未发号显示占位', () => {
    expect(
      renderLines(['{model}{bin}', '{yyww} {trace}'], {
        model: 'M',
        yyww: '2642',
        trace: null,
        bin: 'B1',
      })
    ).toEqual(['MB1', '2642 ••••'])
  })
  it('起草人不能自批', () => {
    expect(isSelfApproval({ created_by: 'a' }, 'a')).toBe(true)
    expect(isSelfApproval({ created_by: 'a' }, 'b')).toBe(false)
    expect(isSelfApproval({ created_by: null }, 'a')).toBe(false)
  })
  it('重打原因：reason_id、comment 必填，comment ≤300', () => {
    expect(reprintErrors({})).toEqual(['reason_id', 'comment'])
    expect(
      reprintErrors({ reason_id: 'R1', comment: 'x'.repeat(301) })
    ).toEqual(['comment_too_long'])
    expect(
      reprintErrors({ reason_id: 'R1', comment: 'x'.repeat(300) })
    ).toEqual([])
  })
  it('追溯码 ≤32、[A-Z0-9-]，规则可配置', () => {
    expect(isValidTraceCode('2642-0001')).toBe(true)
    expect(isValidTraceCode('a1')).toBe(false)
    expect(isValidTraceCode('A'.repeat(33))).toBe(false)
    expect(isValidTraceCode('abc', { maxLength: 4, pattern: /^[a-z]+$/ })).toBe(
      true
    )
    expect(TRACE_CODE_RULE.maxLength).toBe(32)
    expect(traceCodeError('A'.repeat(33))).toBe('max_length')
    expect(traceCodeError('ab')).toBe('pattern')
  })
  it('读回码不一致强制 fail', () => {
    expect(effectiveResult({ result: 'pass', read_code: 'X' }, 'Y')).toBe(
      'fail'
    )
    expect(effectiveResult({ result: 'pass', read_code: 'Y' }, 'Y')).toBe(
      'pass'
    )
  })
  it('超过 6 位小数', () => {
    expect(tooManyPlaces('1.1234567')).toBe(true)
    expect(tooManyPlaces('1.123456')).toBe(false)
  })
  it('请求体白名单不含 seq / source', () => {
    expect(MARKING_BODY.mark).not.toContain('seq')
    expect(MARKING_BODY.mark).not.toContain('source')
  })
})

describe('模板 mock', () => {
  it('版本对比：逐字段、逐行', async () => {
    const all = await api.templates()
    const [v1, v2] = [all[0], all[1]]
    expect(siblingVersions(all, v2).map((x) => x.id)).toEqual(['t1'])
    expect(diffTemplates(v1, v2)).toEqual([
      { field: 'date_code_basis', before: 'lot_start', after: 'marking' },
      { field: 'lines', line: 2, before: '{yyww}', after: '{yyww} {trace}' },
    ])
  })
  it('起草人审批 409 self_approval；他人审批后旧版本 retired', async () => {
    setMarkingMockUser('eng1')
    const t = await api.createTemplate({
      code: 'MK-QFN32-ACME',
      product_id: 'p1',
      customer_id: 'c1',
      lines: ['{model}', ''],
      date_code_basis: 'marking',
      uses_bin: false,
    })
    expect(t.version).toBe(3)
    expect(t.lines).toEqual(['{model}'])
    expect(await detail(api.approve(t.id))).toMatchObject({
      status: 409,
      detail: { code: 'self_approval' },
    })
    setMarkingMockUser('qa1')
    await api.approve(t.id)
    const all = await api.templates()
    expect(all.find((x) => x.id === 't2')!.status).toBe('retired')
    expect(
      await detail(api.updateTemplate(t.id, { lines: ['x'] }))
    ).toMatchObject({ status: 409, detail: { code: 'template_readonly' } })
  })
})

describe('打标作业 mock（D78）', () => {
  it('没有已批准模板 409 marking_template_missing', async () => {
    expect(await detail(api.preview('lot3'))).toMatchObject({
      status: 409,
      detail: { code: 'marking_template_missing' },
    })
  })
  it('预览日期码按站点日期', async () => {
    const p = await api.preview('lot1')
    expect(p.date_code).toBe('2642')
    expect(p.trace_code).toBeNull()
  })
  it('缺 Idempotency-Key 422 missing（loc=header）', async () => {
    expect(await detail(api.mark({ lot_id: 'lot1' }))).toMatchObject({
      status: 422,
      detail: [{ type: 'missing', loc: ['header', 'Idempotency-Key'] }],
    })
  })
  it('首打 seq=1；同 key 重放返回原结果不占新号；不同内容 422', async () => {
    const r1 = await api.mark({ lot_id: 'lot1', equipment_id: 'LM-01' }, 'k1')
    const r2 = await api.mark({ lot_id: 'lot1', equipment_id: 'LM-01' }, 'k1')
    expect(r2).toEqual(r1)
    expect(r1.prints.map((p) => p.seq)).toEqual([1])
    expect(r1.trace_code).toBe('26420001')
    expect(
      await detail(api.mark({ lot_id: 'lot1', equipment_id: 'LM-02' }, 'k1'))
    ).toMatchObject({
      status: 422,
      detail: [{ type: 'idempotency_key_reused' }],
    })
  })
  it('数量超 6 位小数 422 value_error ctx.max_places', async () => {
    expect(
      await detail(api.mark({ lot_id: 'lot1', qty: '1.1234567' }, 'kq'))
    ).toMatchObject({
      status: 422,
      detail: [{ type: 'value_error', ctx: { max_places: 6 } }],
    })
  })
  it('检验 OCR 不一致记 fail；重打必填原因、追加 seq=2、号不变', async () => {
    const r = await api.mark({ lot_id: 'lot1' }, 'k1')
    const i = await api.inspect(
      r.id,
      { result: 'pass', read_code: '26420002' },
      'ki'
    )
    expect(i.latest_inspection_status).toBe('fail')
    expect(i.inspections[0]).toMatchObject({
      expected_code: '26420001',
      read_code: '26420002',
    })
    expect(
      await detail(api.mark({ lot_id: 'lot1', record_id: r.id }, 'kr0'))
    ).toMatchObject({
      status: 422,
      detail: [{ type: 'missing', loc: ['body', 'reason_id'] }],
    })
    const re = {
      lot_id: 'lot1',
      record_id: r.id,
      reason_id: 'R1',
      comment: '模糊',
    }
    const r2 = await api.mark(re, 'kr1')
    const again = await api.mark(re, 'kr1')
    expect(again.prints.length).toBe(2)
    expect(r2.prints.map((p) => p.seq)).toEqual([1, 2])
    expect(r2.reprint_count).toBe(1)
    expect(r2.trace_code).toBe(r.trace_code)
    expect(r2.latest_inspection_status).toBe('pending')
    expect(inspectionsByPrint(r2).map((g) => g.inspections.length)).toEqual([
      1, 0,
    ])
  })
  it('报废对象 409 invalid_transition', async () => {
    expect(await detail(api.mark({ lot_id: 'lot4' }, 'ks'))).toMatchObject({
      status: 409,
      detail: { code: 'invalid_transition' },
    })
    const r = await api.mark({ lot_id: 'lot1' }, 'k1')
    scrapMarkingMockRecord(r.id)
    expect(
      await detail(api.inspect(r.id, { result: 'pass' }, 'ki'))
    ).toMatchObject({ status: 409, detail: { code: 'invalid_transition' } })
  })
  it('作废：原因必填；作废后打印 / 检验 / 作废 409；读回码格式 422 ctx.reason', async () => {
    const r = await api.mark({ lot_id: 'lot1' }, 'k1')
    expect(
      await detail(api.inspect(r.id, { result: 'pass', read_code: 'ab' }, 'kx'))
    ).toMatchObject({
      status: 422,
      detail: [{ type: 'value_error', ctx: { reason: 'pattern' } }],
    })
    expect(
      await detail(api.void(r.id, { reason_id: 'V1', comment: '' }, 'kv0'))
    ).toMatchObject({
      status: 422,
      detail: [{ type: 'missing', loc: ['body', 'comment'] }],
    })
    const v = await api.void(r.id, { reason_id: 'V1', comment: '错批' }, 'kv1')
    expect(v.voided).toBe(true)
    expect(
      await detail(api.inspect(r.id, { result: 'pass' }, 'ki'))
    ).toMatchObject({ status: 409, detail: { code: 'invalid_transition' } })
    expect(
      await detail(api.void(r.id, { reason_id: 'V1', comment: 'x' }, 'kv2'))
    ).toMatchObject({ status: 409 })
  })
  it('EAP 回报号不一致 409 trace_code_mismatch', async () => {
    const r = await api.mark({ lot_id: 'lot1' }, 'k1')
    expect(
      await detail(
        mockEapPrintReport(r.id, { trace_code: 'X', external_event_id: 'e1' })
      )
    ).toMatchObject({
      status: 409,
      detail: {
        code: 'trace_code_mismatch',
        ctx: { expected: r.trace_code, actual: 'X' },
      },
    })
  })
  it('marked_at 范围半开区间：等于结束边界不含，等于开始边界含', async () => {
    await api.mark({ lot_id: 'lot1' }, 'k1')
    const at = '2026-10-14T17:00:00.000Z'
    expect(await api.records({ marked_at_from: at })).toHaveLength(1)
    expect(await api.records({ marked_at_to: at })).toHaveLength(0)
  })
})

describe('追溯码 mock（B3）', () => {
  it('按追溯码反查批次和晶圆；格式不符 422；作废后查不到', async () => {
    const { mockTraceByCode } = await import('./marking')
    const r = await api.mark({ lot_id: 'lot1' }, 'k1')
    const tr = await mockTraceByCode(r.trace_code)
    expect(tr.target.code).toBe('LOT-A001')
    expect(tr.wafers).toHaveLength(25)
    expect(await detail(mockTraceByCode('ab'))).toMatchObject({
      status: 422,
      detail: [{ ctx: { reason: 'pattern' } }],
    })
    await api.void(r.id, { reason_id: 'V', comment: 'x' }, 'kv')
    expect(await detail(mockTraceByCode(r.trace_code))).toMatchObject({
      status: 404,
    })
  })
})

describe('D78 补充三', () => {
  it('追溯码违反两条规则返回两条 422', async () => {
    const { traceCodeErrors, mockTraceByCode } = await import('./marking')
    expect(traceCodeErrors('a'.repeat(33))).toEqual(['max_length', 'pattern'])
    expect(await detail(mockTraceByCode('a'.repeat(33)))).toMatchObject({
      status: 422,
      detail: [
        { ctx: { reason: 'max_length', max_length: 32 } },
        { ctx: { reason: 'pattern', pattern: '^[A-Z0-9-]+$' } },
      ],
    })
  })
  it('config：mock 返回默认；缺失或非法时退回默认', async () => {
    const { ruleFromConfig } = await import('./marking')
    expect(await api.config()).toEqual({
      trace_code_max_length: 32,
      trace_code_pattern: '^[A-Z0-9-]+$',
    })
    expect(ruleFromConfig(null).maxLength).toBe(32)
    const r = ruleFromConfig({
      trace_code_max_length: 8,
      trace_code_pattern: '(',
    })
    expect(r.maxLength).toBe(8)
    expect(r.pattern.source).toBe('^[A-Z0-9-]+$')
  })
  it('void 缺 Idempotency-Key 422', async () => {
    const r = await api.mark({ lot_id: 'lot1' }, 'k1')
    expect(
      await detail(api.void(r.id, { reason_id: 'V', comment: 'x' }))
    ).toMatchObject({
      status: 422,
      detail: [{ loc: ['header', 'Idempotency-Key'] }],
    })
  })
})
