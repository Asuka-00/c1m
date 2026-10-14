import type { AxiosError } from 'axios'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  type InspectInput,
  diffTemplates,
  effectiveResult,
  inspectionsByPrint,
  isoYyww,
  isSelfApproval,
  codeLength,
  markingMockLeaveStep,
  isAllowedTracePattern,
  hasLeftMarkingStep,
  readCodeErrors,
  canInspect,
  canReprint,
  isValidTraceCode,
  MARKING_POLICY,
  MARKING_BODY,
  mockEapPrintReport,
  mockMarkingApi as api,
  renderLines,
  reprintErrors,
  resetMarkingMock,
  ruleFromConfig,
  scrapMarkingMockRecord,
  setMarkingMockConfig,
  setMarkingMockNow,
  setMarkingMockUser,
  siblingVersions,
  traceCodeError,
  traceCodeErrors,
  trackOutBlock,
  TRACE_CODE_RULE,
  unknownPlaceholders,
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

/** 建主记录 + 首打。 */
const firstPrint = async (lot = 'lot1', k = 'k1') => {
  const r = await api.create({ lot_id: lot }, `${k}-c`)
  return api.print(r.id, {}, `${k}-p`)
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
  it('D79 占位符替换，未发号显示占位', () => {
    expect(
      renderLines(
        [
          '{product_code}-{customer_code}',
          '{date_code} {trace_code}',
          '{lot_id}',
        ],
        {
          trace_code: null,
          date_code: '2642',
          lot_id: 'L1',
          product_code: 'P',
          customer_code: 'C',
        }
      )
    ).toEqual(['P-C', '2642 ••••', 'L1'])
  })
  it('D79 白名单外占位符', () => {
    expect(
      unknownPlaceholders(['{trace_code}', '{model} {yyww}', '{model}'])
    ).toEqual(['model', 'yyww'])
    expect(unknownPlaceholders(['{date_code}{lot_id}'])).toEqual([])
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
  it('追溯码规则可配置', () => {
    expect(isValidTraceCode('2642-0001')).toBe(true)
    expect(isValidTraceCode('a1')).toBe(false)
    expect(traceCodeError('A'.repeat(33))).toBe('max_length')
    expect(TRACE_CODE_RULE.maxLength).toBe(32)
    const r = ruleFromConfig({
      trace_code_max_length: 4,
      trace_code_pattern: '^[A-Z]+$',
    })
    expect(traceCodeErrors('ABCDE', r)).toEqual(['max_length'])
    expect(traceCodeErrors('AB1', r)).toEqual(['pattern'])
    const bad = ruleFromConfig({
      trace_code_max_length: 8,
      trace_code_pattern: '(',
    })
    // QA F6：正则非法 → 不做格式预校验
    expect(bad.pattern).toBeNull()
    expect(traceCodeErrors('anything', bad)).toEqual([])
    expect(ruleFromConfig(null).maxLength).toBe(32)
  })
  it('读回码不一致强制 fail', () => {
    expect(effectiveResult({ result: 'pass', read_code: 'X' }, 'Y')).toBe(
      'fail'
    )
    expect(effectiveResult({ result: 'pass', read_code: 'Y' }, 'Y')).toBe(
      'pass'
    )
  })
  it('请求体白名单：无 seq / source / qty', () => {
    for (const k of ['seq', 'source', 'qty']) {
      expect(MARKING_BODY.create).not.toContain(k)
      expect(MARKING_BODY.print).not.toContain(k)
    }
  })
})

describe('D78 补充五：纯空白只认 /^[ \\t\\r\\n\\u3000]*$/', () => {
  it.each([
    ['末尾带 \\n', 'AB12\n', ['pattern']],
    ['开头带 \\n', '\nAB12', ['pattern']],
    ['中间带空格', 'AB 12', ['pattern']],
    ['全角 ＡＢＣ', 'ＡＢＣ', ['pattern']],
    ['刚好 32 位', 'A'.repeat(32), []],
    ['33 位', 'A'.repeat(33), ['max_length']],
    ['33 位且含小写', 'a'.repeat(33), ['max_length', 'pattern']],
    ['只有一个 -', '-', []],
    ['U+3000', '\u3000', ['missing']],
    ['空格 + \\t\\r\\n + U+3000', ' \t\r\n\u3000', ['missing']],
    ['U+FEFF', '\ufeff', ['pattern']],
    ['\\x1f', '\x1f', ['pattern']],
    ['空串', '', ['missing']],
  ])('%s', (_, v, want) => {
    expect(traceCodeErrors(v)).toEqual(want)
  })
})

describe('模板 mock（D79）', () => {
  it('版本对比：逐字段、逐行', async () => {
    const all = await api.templates()
    const [v1, v2] = [all[0], all[1]]
    expect(siblingVersions(all, v2).map((x) => x.id)).toEqual(['t1'])
    expect(diffTemplates(v1, v2)).toEqual([
      { field: 'date_code_basis', before: 'lot_start', after: 'marking' },
      {
        field: 'lines',
        line: 2,
        before: '{date_code}',
        after: '{date_code} {trace_code}',
      },
    ])
    expect(v2.product_name).toBe('QFN32-A')
    expect(v2.customer_name).toBe('ACME')
  })
  it('白名单外占位符 422 value_error ctx.reason=unknown_placeholder', async () => {
    expect(
      await detail(
        api.createTemplate({
          code: 'X',
          product_id: 'p3',
          customer_id: 'c1',
          lines: ['{model}'],
          date_code_basis: 'marking',
          uses_bin: false,
        })
      )
    ).toMatchObject({
      status: 422,
      detail: [
        {
          type: 'value_error',
          ctx: { reason: 'unknown_placeholder', placeholder: 'model' },
        },
      ],
    })
  })
  it('新版本复制最新版本为草稿、版本号递增；已有草稿 409 draft_exists', async () => {
    setMarkingMockUser('eng1')
    const d = await api.newVersion('t1')
    expect(d).toMatchObject({ version: 3, status: 'draft', created_by: 'eng1' })
    expect(d.lines).toEqual(['{product_code}', '{date_code} {trace_code}'])
    expect(await detail(api.newVersion('t2'))).toMatchObject({
      status: 409,
      detail: { code: 'draft_exists' },
    })
  })
  it('自批 422 value_error ctx.reason=self_approval；他人审批后旧版本 retired；已批准改动 409', async () => {
    setMarkingMockUser('eng1')
    const t = await api.newVersion('t2')
    expect(await detail(api.approve(t.id))).toMatchObject({
      status: 422,
      detail: [{ type: 'value_error', ctx: { reason: 'self_approval' } }],
    })
    setMarkingMockUser('qa1')
    await api.approve(t.id)
    const all = await api.templates()
    expect(all.find((x) => x.id === 't2')!.status).toBe('retired')
    expect(
      await detail(api.updateTemplate(t.id, { lines: ['x'] }))
    ).toMatchObject({
      status: 409,
      detail: { code: 'template_readonly' },
    })
  })
})

describe('打标作业 mock（D78/D79）', () => {
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
    expect(p.lines).toEqual(['FS3201', '2642 ••••'])
  })
  it('缺 Idempotency-Key 422 missing（loc=header）', async () => {
    expect(await detail(api.create({ lot_id: 'lot1' }))).toMatchObject({
      status: 422,
      detail: [{ type: 'missing', loc: ['header', 'Idempotency-Key'] }],
    })
    const r = await api.create({ lot_id: 'lot1' }, 'c')
    for (const p of [
      api.print(r.id, {}),
      api.inspect(r.id, { result: 'pass', read_code: r.trace_code }),
      api.void(r.id, { reason_id: 'V', comment: 'x' }),
    ])
      expect(await detail(p)).toMatchObject({
        status: 422,
        detail: [{ loc: ['header', 'Idempotency-Key'] }],
      })
  })
  it('建主记录不打印；首打走 prints（seq=1）；同 key 重放不占新 seq；不同内容 422', async () => {
    const r = await api.create({ lot_id: 'lot1', equipment_id: 'LM-01' }, 'c1')
    expect(r.prints).toEqual([])
    expect(r.trace_code).toBe('26420001')
    const p1 = await api.print(r.id, {}, 'p1')
    const again = await api.print(r.id, {}, 'p1')
    expect(again).toEqual(p1)
    expect(p1.prints.map((p) => p.seq)).toEqual([1])
    expect(
      await detail(api.print(r.id, { equipment_id: 'X' }, 'p1'))
    ).toMatchObject({
      status: 422,
      detail: { code: 'idempotency_key_reused' },
    })
    expect(await detail(api.create({ lot_id: 'lot1' }, 'c2'))).toMatchObject({
      status: 409,
      detail: { code: 'already_marked' },
    })
  })
  it('pass 但读回不一致：强制 fail，响应带 result_overridden', async () => {
    const r = await firstPrint()
    const o = await api.inspect(
      r.id,
      { result: 'pass', read_code: '26420002' },
      'ki'
    )
    expect(o).toMatchObject({
      result: 'fail',
      expected_code: '26420001',
      read_code: '26420002',
      result_overridden: true,
    })
    expect(o.record.latest_inspection_status).toBe('fail')
    expect(o.record.inspections[0].result_overridden).toBe(true)
  })
  it('重打必填原因、seq=2、号不变、检验回到 pending', async () => {
    const r = await firstPrint()
    await api.inspect(r.id, { result: 'fail', read_code: r.trace_code }, 'ki')
    expect(await detail(api.print(r.id, {}, 'kr0'))).toMatchObject({
      status: 422,
      detail: [{ type: 'missing', loc: ['body', 'reason_id'] }],
    })
    const re = { reason_id: 'R1', comment: '模糊' }
    const r2 = await api.print(r.id, re, 'kr1')
    const again = await api.print(r.id, re, 'kr1')
    expect(again.prints.length).toBe(2)
    expect(r2.prints.map((p) => p.seq)).toEqual([1, 2])
    expect(r2.reprint_count).toBe(1)
    expect(r2.trace_code).toBe(r.trace_code)
    expect(r2.latest_inspection_status).toBe('pending')
    expect(inspectionsByPrint(r2).map((g) => g.inspections.length)).toEqual([
      1, 0,
    ])
  })
  it('作废后同一批次可重新首打：新主记录、新号、seq 从 1 开始', async () => {
    const r = await firstPrint()
    await api.void(r.id, { reason_id: 'V1', comment: '错批' }, 'kv')
    const n = await firstPrint('lot1', 'k2')
    expect(n.id).not.toBe(r.id)
    expect(n.trace_code).toBe('26420002')
    expect(n.prints.map((p) => p.seq)).toEqual([1])
    // D81：重打缺原因 422 先于作废 409
    expect(await detail(api.print(r.id, {}, 'kx'))).toMatchObject({
      status: 422,
      detail: [{ type: 'missing', loc: ['body', 'reason_id'] }],
    })
    expect(
      await detail(api.print(r.id, { reason_id: 'R1', comment: '重打' }, 'kx2'))
    ).toMatchObject({
      status: 409,
      detail: { code: 'invalid_transition' },
    })
  })
  it('作废：原因必填；作废后检验 / 作废 409；读回码格式 422', async () => {
    const r = await firstPrint()
    // D79 补充二-3：读回码不校验格式，不一致强制 fail
    expect(
      await api.inspect(r.id, { result: 'pass', read_code: 'ab' }, 'kx')
    ).toMatchObject({ result: 'fail', result_overridden: true })
    expect(
      await detail(api.inspect(r.id, { result: 'pass', read_code: '  ' }, 'kw'))
    ).toMatchObject({
      status: 422,
      detail: [{ type: 'missing', loc: ['body', 'read_code'] }],
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
      await detail(
        api.inspect(r.id, { result: 'pass', read_code: r.trace_code }, 'ki')
      )
    ).toMatchObject({
      status: 409,
      detail: { code: 'invalid_transition' },
    })
    expect(
      await detail(api.void(r.id, { reason_id: 'V1', comment: 'x' }, 'kv2'))
    ).toMatchObject({
      status: 409,
    })
  })
  it('报废对象 409 invalid_transition', async () => {
    expect(await detail(api.create({ lot_id: 'lot4' }, 'ks'))).toMatchObject({
      status: 409,
      detail: { code: 'invalid_transition' },
    })
    const r = await firstPrint()
    scrapMarkingMockRecord(r.id)
    expect(
      await detail(
        api.inspect(r.id, { result: 'pass', read_code: r.trace_code }, 'ki')
      )
    ).toMatchObject({
      status: 409,
      detail: { code: 'invalid_transition' },
    })
  })
  it('EAP 回报号不一致 409 trace_code_mismatch', async () => {
    const r = await firstPrint()
    expect(
      await detail(
        mockEapPrintReport('lot1', { trace_code: 'X', external_event_id: 'e1' })
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
    await firstPrint()
    const at = '2026-10-14T17:00:00.000Z'
    expect(await api.records({ marked_at_from: at })).toHaveLength(1)
    expect(await api.records({ marked_at_to: at })).toHaveLength(0)
  })
  it('config：mock 返回默认', async () => {
    expect(await api.config()).toEqual({
      trace_code_max_length: 32,
      trace_code_pattern: '^[A-Z0-9-]+$',
    })
  })
})

describe('kind=trace_code 追溯（D79-6）', () => {
  it('结果形状；默认不含已作废，include_voided=true 才含；格式不符逐条 422', async () => {
    const r = await firstPrint()
    await api.inspect(r.id, { result: 'pass', read_code: r.trace_code }, 'ki')
    expect(await api.trace(r.trace_code)).toEqual({
      marking_id: r.id,
      lot_id: 'lot1',
      trace_code: r.trace_code,
      voided: false,
      prints: [
        {
          print_id: r.prints[0].id,
          seq: 1,
          marked_at: r.prints[0].printed_at,
          latest_inspection_result: 'pass',
        },
      ],
    })
    await api.void(r.id, { reason_id: 'V', comment: 'x' }, 'kv')
    expect(await detail(api.trace(r.trace_code))).toMatchObject({ status: 404 })
    expect((await api.trace(r.trace_code, true)).voided).toBe(true)
    expect(await detail(api.trace('a'.repeat(33)))).toMatchObject({
      status: 422,
      detail: [
        { ctx: { reason: 'max_length', max_length: 32 } },
        { ctx: { reason: 'pattern', pattern: '^[A-Z0-9-]+$' } },
      ],
    })
  })
})

describe('D79 补充', () => {
  it('result_overridden 未改写时为 false', async () => {
    const r = await firstPrint()
    const o = await api.inspect(
      r.id,
      { result: 'pass', read_code: r.trace_code },
      'ki'
    )
    expect(o.result_overridden).toBe(false)
    expect(o.record.inspections[0].result_overridden).toBe(false)
  })
  it('作废后旧主记录保留检验状态；出站只看未作废主记录', async () => {
    const r = await firstPrint()
    await api.inspect(r.id, { result: 'fail', read_code: r.trace_code }, 'ki')
    const v = await api.void(r.id, { reason_id: 'V', comment: 'x' }, 'kv')
    expect(v.latest_inspection_status).toBe('fail')
    expect(trackOutBlock([v])).toBe('not_marked')
    expect(trackOutBlock([v], false)).toBeNull()
    const n = await firstPrint('lot1', 'k2')
    expect(trackOutBlock([v, n])).toBe('pending')
    const ok = await api.inspect(
      n.id,
      { result: 'pass', read_code: n.trace_code },
      'ki2'
    )
    expect(trackOutBlock([v, ok.record])).toBeNull()
  })
  it('EAP 上报找不到未作废主记录 409 no_active_marking', async () => {
    const r = await firstPrint()
    await api.void(r.id, { reason_id: 'V', comment: 'x' }, 'kv')
    expect(
      await detail(
        mockEapPrintReport('lot1', {
          trace_code: r.trace_code,
          external_event_id: 'e1',
        })
      )
    ).toMatchObject({ status: 409, detail: { code: 'no_active_marking' } })
  })
})

describe('QA 评审 F1–F5（口径集中在 MARKING_POLICY）', () => {
  const saved = { ...MARKING_POLICY }
  afterEach(() => Object.assign(MARKING_POLICY, saved))

  it('F3 长度口径：utf16 与 codepoint', () => {
    const v = 'A'.repeat(31) + '😀'
    expect(codeLength(v, 'utf16')).toBe(33)
    expect(codeLength(v, 'codepoint')).toBe(32)
    // D79 补充二-2：默认按码点
    expect(traceCodeErrors(v)).toEqual(['pattern'])
    expect(
      traceCodeErrors(v, { ...TRACE_CODE_RULE, lengthMode: 'utf16' })
    ).toEqual(['max_length', 'pattern'])
    expect(
      traceCodeErrors(v, { ...TRACE_CODE_RULE, lengthMode: 'codepoint' })
    ).toEqual(['pattern'])
  })
  it('F2 读回码不校验格式时：格式不符按不一致强制 fail，纯空白 422 missing', async () => {
    MARKING_POLICY.validateReadCodeFormat = false
    const r = await firstPrint()
    expect(
      await detail(
        api.inspect(r.id, { result: 'pass', read_code: ' \t' }, 'kw')
      )
    ).toMatchObject({ status: 422, detail: [{ type: 'missing' }] })
    const o = await api.inspect(
      r.id,
      { result: 'pass', read_code: 'abc' },
      'ki'
    )
    expect(o).toMatchObject({ result: 'fail', result_overridden: true })
  })
  it('D79 补充二-1：同一次打印可多次检验，以最新为准；离开打标工步后 409', async () => {
    const r = await firstPrint()
    await api.inspect(r.id, { result: 'pass', read_code: r.trace_code }, 'ki1')
    const o = await api.inspect(
      r.id,
      { result: 'fail', read_code: r.trace_code },
      'ki2'
    )
    expect(o.record.latest_inspection_status).toBe('fail')
    expect(o.record.inspections.map((i) => i.seq)).toEqual([1, 1])
    expect(canInspect(o.record)).toBe(true)
    markingMockLeaveStep('lot1')
    // QA N-F3：有工步信息且已离开时禁用检验
    const left = (await api.records({ lot_id: 'lot1' }))[0]
    expect(hasLeftMarkingStep(left)).toBe(true)
    expect(canInspect(left)).toBe(false)
    expect(canInspect({ ...left, at_marking_step: undefined })).toBe(true)
    expect(
      await detail(
        api.inspect(r.id, { result: 'pass', read_code: r.trace_code }, 'ki3')
      )
    ).toMatchObject({
      status: 409,
      detail: { code: 'invalid_transition' },
    })
  })
  it('D79 补充二-3：读回码不校验格式；超过 128 码点 422 max_length', async () => {
    const r = await firstPrint()
    expect(readCodeErrors('😀'.repeat(128))).toEqual([])
    expect(readCodeErrors('😀'.repeat(129))).toEqual(['max_length'])
    expect(readCodeErrors('\u3000')).toEqual(['missing'])
    expect(
      await detail(
        api.inspect(r.id, { result: 'pass', read_code: 'x'.repeat(129) }, 'kl')
      )
    ).toMatchObject({
      status: 422,
      detail: [
        { type: 'value_error', ctx: { reason: 'max_length', max_length: 128 } },
      ],
    })
  })
  it('D79 补充三：read_code 缺字段/null/空串/纯空白 422 missing，不入库不记 fail', async () => {
    const r = await firstPrint()
    const bads: unknown[] = [undefined, null, '', ' \t\r\n\u3000']
    for (const [n, v] of bads.entries()) {
      const body = (
        v === undefined ? { result: 'pass' } : { result: 'pass', read_code: v }
      ) as InspectInput
      expect(await detail(api.inspect(r.id, body, `m${n}`))).toMatchObject({
        status: 422,
        detail: [{ type: 'missing', loc: ['body', 'read_code'] }],
      })
    }
    expect(
      await detail(
        api.inspect(
          r.id,
          { result: 'pass', read_code: 123 as unknown as string },
          'st'
        )
      )
    ).toMatchObject({
      status: 422,
      detail: [{ type: 'string_type', loc: ['body', 'read_code'] }],
    })
    const after = (await api.records({ lot_id: 'lot1' }))[0]
    expect(after.inspections).toHaveLength(0)
    expect(after.latest_inspection_status).toBe('pending')
  })
  it('D79 补充三：其余原值不 trim；U+FEFF、\\x1f 按普通字符，不一致强制 fail', async () => {
    const r = await firstPrint()
    expect(readCodeErrors('\uFEFF')).toEqual([])
    expect(readCodeErrors('\x1f')).toEqual([])
    for (const [n, v] of [
      ` ${r.trace_code}`,
      `\uFEFF${r.trace_code}`,
      '\x1f',
    ].entries()) {
      const o = await api.inspect(
        r.id,
        { result: 'pass', read_code: v },
        `f${n}`
      )
      expect(o).toMatchObject({
        result: 'fail',
        result_overridden: true,
        read_code: v,
      })
    }
    const ok = await api.inspect(
      r.id,
      { result: 'pass', read_code: r.trace_code },
      'ok'
    )
    expect(ok).toMatchObject({ result: 'pass', result_overridden: false })
  })
  it('D79 补充二-4：配置正则只允许正向字符类', () => {
    expect(
      ruleFromConfig({ trace_code_pattern: '^[A-Z0-9-]+$' }).pattern?.source
    ).toBe('^[A-Z0-9-]+$')
    for (const ok of [
      '^[A-Z]+$',
      '^[0-9]+$',
      '^[A-F0-9]+$',
      '^[A-Z0-9-]+$',
      '^[ABC1-3-]+$',
    ])
      expect(isAllowedTracePattern(ok)).toBe(true)
    // QA N-F1：反斜杠、小写、_、- 在中间、降序区间、跨类区间、空类都拒
    for (const bad of [
      '^[A-Z\\-]+$',
      '^[\\w]+$',
      '^[A-Z\\]]+$',
      '^[a-z]+$',
      '^[A-Z_]+$',
      '^[A-Z-0-9]+$',
      '^[-A-Z]+$',
      '^[Z-A]+$',
      '^[9-0]+$',
      '^[0-Z]+$',
      '^[]+$',
      '^[A-Z][0-9]+$',
    ])
      expect(isAllowedTracePattern(bad), bad).toBe(false)
    expect(
      ruleFromConfig({ trace_code_pattern: '^[A-Z\\-]+$' }).pattern
    ).toBeNull()
    for (const bad of [
      '^[^a-z]+$',
      '^A+$',
      '[A-Z]+',
      '^[A-Z]*$',
      '^(A|B)+$',
      '^[A-Z]+$|x',
    ])
      expect(ruleFromConfig({ trace_code_pattern: bad }).pattern).toBeNull()
  })
  it('D79 补充二-6：marked_at 取首打时间不变，last_printed_at 跟随重打；按首打时间筛选', async () => {
    const c = await api.create({ lot_id: 'lot1' }, 'c')
    expect(c.marked_at).toBeNull()
    expect(
      await api.records({ marked_at_from: '2000-01-01T00:00:00Z' })
    ).toHaveLength(0)
    const p1 = await api.print(c.id, {}, 'p1')
    setMarkingMockNow(() => new Date('2026-10-15T03:00:00Z'))
    const p2 = await api.print(c.id, { reason_id: 'R', comment: 'x' }, 'p2')
    expect(p2.marked_at).toBe(p1.marked_at)
    expect(p2.last_printed_at).toBe('2026-10-15T03:00:00.000Z')
    expect(
      await api.records({ marked_at_to: '2026-10-15T00:00:00Z' })
    ).toHaveLength(1)
    expect(
      await api.records({ marked_at_from: '2026-10-15T00:00:00Z' })
    ).toHaveLength(0)
  })
  it('F5 重打不限于 fail；F4 空行不丢', async () => {
    const r = await firstPrint()
    expect(canReprint(r)).toBe(true)
    const r2 = await api.print(r.id, { reason_id: 'R', comment: '缺损' }, 'kr')
    expect(r2.prints).toHaveLength(2)
    const t = await api.createTemplate({
      code: 'X',
      product_id: 'p3',
      customer_id: 'c1',
      lines: ['{product_code}', '', '{date_code}'],
      date_code_basis: 'marking',
      uses_bin: false,
    })
    expect(t.lines).toEqual(['{product_code}', '', '{date_code}'])
  })
})

describe('D79 补充四：超长 / 格式 422 的 ctx 字段', () => {
  it('trace_code 的 max_length 取 config，pattern 为 config 原样正则', async () => {
    setMarkingMockConfig({
      trace_code_max_length: 4,
      trace_code_pattern: '^[A-F0-9]+$',
    })
    expect(await api.config()).toEqual({
      trace_code_max_length: 4,
      trace_code_pattern: '^[A-F0-9]+$',
    })
    expect(await detail(api.trace('ABCXYZ'))).toEqual({
      status: 422,
      detail: [
        expect.objectContaining({
          type: 'value_error',
          loc: ['body', 'code'],
          ctx: { reason: 'max_length', max_length: 4 },
        }),
        expect.objectContaining({
          type: 'value_error',
          loc: ['body', 'code'],
          ctx: { reason: 'pattern', pattern: '^[A-F0-9]+$' },
        }),
      ],
    })
  })
  it('read_code 的 max_length 固定 128，不随 config 变，也不报 pattern', async () => {
    setMarkingMockConfig({ trace_code_max_length: 4 })
    const r = await firstPrint()
    expect(
      await detail(
        api.inspect(r.id, { result: 'pass', read_code: 'x'.repeat(129) }, 'k')
      )
    ).toMatchObject({
      status: 422,
      detail: [
        {
          type: 'value_error',
          ctx: { reason: 'max_length', max_length: 128 },
        },
      ],
    })
  })
  it('resetMarkingMock 恢复默认 config', async () => {
    setMarkingMockConfig({ trace_code_max_length: 4 })
    resetMarkingMock()
    expect((await api.config()).trace_code_max_length).toBe(32)
  })
})

describe('N-E2：mock 校验顺序 缺 key → 请求体 422 → 幂等重放 → 409', () => {
  it('检验：缺 key 优先于 body；body 422 优先于 left_step 409；重放优先于 409', async () => {
    const r = await firstPrint()
    const bad = { result: 'pass', read_code: '' } as InspectInput
    expect(
      await detail(api.inspect(r.id, bad, undefined as never))
    ).toMatchObject({
      status: 422,
      detail: [{ loc: ['header', 'Idempotency-Key'], type: 'missing' }],
    })
    const ok = { result: 'pass', read_code: r.trace_code } as InspectInput
    const first = await api.inspect(r.id, ok, 'ord1')
    markingMockLeaveStep('lot1')
    expect(await detail(api.inspect(r.id, bad, 'ord2'))).toMatchObject({
      status: 422,
      detail: [{ loc: ['body', 'read_code'], type: 'missing' }],
    })
    expect(await api.inspect(r.id, ok, 'ord1')).toEqual(first)
    expect(await detail(api.inspect(r.id, ok, 'ord3'))).toMatchObject({
      status: 409,
    })
  })
  it('检验完全不带 read_code → 422 missing', async () => {
    const r = await firstPrint()
    expect(
      await detail(api.inspect(r.id, { result: 'pass' } as InspectInput, 'nr'))
    ).toMatchObject({
      status: 422,
      detail: [{ loc: ['body', 'read_code'], type: 'missing' }],
    })
  })
  it('作废：body 422 先于 409 invalid_transition', async () => {
    const r = await firstPrint()
    scrapMarkingMockRecord(r.id)
    expect(
      await detail(api.void(r.id, { reason_id: '', comment: '' }, 'v1'))
    ).toMatchObject({ status: 422 })
    expect(
      await detail(api.void(r.id, { reason_id: 'V', comment: 'c' }, 'v2'))
    ).toMatchObject({ status: 409 })
  })
})
