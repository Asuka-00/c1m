import type { AxiosError } from 'axios'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  mockMarkingApi as api,
  mockTrackOutMarkingCheck,
  reprintErrors,
  resetMarkingMock,
  setMarkingMockNow,
  setMarkingMockUser,
} from '@/lib/api/mes/marking'
import { markingErrorMessage } from './marking-rules'

// F4：mock 对齐 B1→B3 契约（D78 / D79 及补充、D81）
const detail = async (p: Promise<unknown>) => {
  try {
    await p
  } catch (e) {
    const r = (e as AxiosError).response!
    return { status: r.status, detail: (r.data as { detail: unknown }).detail }
  }
  throw new Error('expected rejection')
}
const err = async (p: Promise<unknown>) => {
  try {
    await p
  } catch (e) {
    return e
  }
  throw new Error('expected rejection')
}

beforeEach(() => {
  resetMarkingMock()
  setMarkingMockNow(() => new Date('2026-10-14T17:00:00Z'))
})
afterEach(async () => {
  resetMarkingMock()
  await i18n.changeLanguage('zh-CN')
})

describe('B1 模板审批', () => {
  it('起草人审批自己的非草稿模板：先 422 self_approval，他人再 409 invalid_transition', async () => {
    const [ok] = await api.templates({ status: 'approved' })
    setMarkingMockUser(ok.created_by!)
    expect(await detail(api.approve(ok.id, 'sa1'))).toMatchObject({
      status: 422,
      detail: [{ type: 'value_error', ctx: { reason: 'self_approval' } }],
    })
    setMarkingMockUser('someone-else')
    expect(await detail(api.approve(ok.id, 'sa2'))).toMatchObject({
      status: 409,
      detail: { code: 'invalid_transition' },
    })
    expect(await detail(api.approve('nope', 'sa3'))).toMatchObject({
      status: 404,
    })
  })
  it('模板四个写接口缺 Idempotency-Key 422 missing（header），同 key 同内容重放', async () => {
    const [ok] = await api.templates({ status: 'approved' })
    const input = {
      code: 'K',
      product_id: 'p3',
      customer_id: 'c1',
      lines: ['{product_code}'],
      date_code_basis: 'marking' as const,
      uses_bin: false,
    }
    // QA P3-1：类型里 key 必填，漏传在 tsc 阶段报错；这里模拟运行时缺头
    // @ts-expect-error key 必填
    api.createTemplate(input).catch(() => {})
    // @ts-expect-error key 必填
    api.updateTemplate(ok.id, { lines: ['x'] }).catch(() => {})
    // @ts-expect-error key 必填
    api.newVersion(ok.id).catch(() => {})
    // @ts-expect-error key 必填
    api.approve(ok.id).catch(() => {})
    const noKey = undefined as unknown as string
    const calls = [
      api.createTemplate(input, noKey),
      api.updateTemplate(ok.id, { lines: ['x'] }, noKey),
      api.newVersion(ok.id, noKey),
      api.approve(ok.id, noKey),
    ]
    for (const c of calls)
      expect(await detail(c)).toMatchObject({
        status: 422,
        detail: [
          {
            loc: ['header', 'Idempotency-Key'],
            type: 'missing',
            code: 'missing',
          },
        ],
      })
    const a = await api.createTemplate(input, 'ck')
    const b = await api.createTemplate(input, 'ck')
    expect(b.id).toBe(a.id)
    expect(
      await detail(api.createTemplate({ ...input, code: 'K2' }, 'ck'))
    ).toMatchObject({ status: 422, detail: { code: 'idempotency_key_reused' } })
  })
  it('修改已批准版本：请求体 422 先于 404 / 409 template_readonly（D81）', async () => {
    const [ok] = await api.templates({ status: 'approved' })
    expect(
      await detail(api.updateTemplate(ok.id, { lines: ['{nope}'] }, 'tk1'))
    ).toMatchObject({
      status: 422,
      detail: [{ type: 'value_error', ctx: { reason: 'unknown_placeholder' } }],
    })
    expect(
      await detail(api.updateTemplate('missing', { lines: ['{nope}'] }, 'tk2'))
    ).toMatchObject({ status: 422 })
    expect(
      await detail(api.updateTemplate('missing', { lines: ['x'] }, 'tk3'))
    ).toMatchObject({ status: 404 })
    expect(
      await detail(api.updateTemplate(ok.id, { lines: ['x'] }, 'tk4'))
    ).toMatchObject({ status: 409, detail: { code: 'template_readonly' } })
  })
  it('self_approval / template_readonly / draft_exists 三语文案', async () => {
    setMarkingMockUser('eng1')
    const [ok] = await api.templates({ status: 'approved' })
    // 最新为 approved 时编辑 409；建草稿后最新变为草稿（同一模板 id）
    const ro = await err(api.updateTemplate(ok.id, { lines: ['x'] }, 'tk8'))
    const d = await api.newVersion(ok.id, 'tk5')
    const self = await err(api.approve(d.id, 'tk6'))
    const dup = await err(api.newVersion(ok.id, 'tk7'))
    for (const lng of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(lng)
      expect(markingErrorMessage(self)).toBe(t('mes.marking.err.selfApproval'))
      expect(markingErrorMessage(dup)).toBe(
        t('mes.marking.code.draft_exists', { expected: '', actual: '' })
      )
      expect(markingErrorMessage(ro)).toBe(
        t('mes.marking.code.template_readonly', { expected: '', actual: '' })
      )
      expect(markingErrorMessage(self)).not.toMatch(/mes\.marking/)
    }
  })
})

describe('B2 发号重打', () => {
  it('重打必须带 reason_id 与 comment；纯空白按正则判 missing（不 trim）', async () => {
    expect(reprintErrors({ reason_id: 'R1', comment: '\u3000 \t' })).toEqual([
      'comment',
    ])
    expect(reprintErrors({ reason_id: 'R1', comment: '\ufeff' })).toEqual([])
    const r = await api.create({ lot_id: 'lot1' }, 'c1')
    await api.print(r.id, {}, 'p1')
    expect(
      await detail(api.print(r.id, { comment: '重打' }, 'p2'))
    ).toMatchObject({
      status: 422,
      detail: [{ type: 'missing', loc: ['body', 'reason_id'] }],
    })
    expect(
      await detail(api.print(r.id, { reason_id: 'R1', comment: ' ' }, 'p3'))
    ).toMatchObject({
      status: 422,
      detail: [{ type: 'missing', loc: ['body', 'comment'] }],
    })
    const ok = await api.print(r.id, { reason_id: 'R1', comment: '糊' }, 'p4')
    expect(ok.prints.map((p) => p.seq)).toEqual([1, 2])
  })
  it('comment 超 300 码点：422 value_error ctx.reason=max_length，先于 404（D79 补充四 / D81）', async () => {
    const long = '𠀀'.repeat(301)
    const e = await detail(
      api.print('missing', { reason_id: 'R1', comment: long }, 'p5')
    )
    expect(e).toMatchObject({
      status: 422,
      detail: [
        {
          type: 'value_error',
          loc: ['body', 'comment'],
          ctx: { reason: 'max_length', max_length: 300 },
        },
      ],
    })
    // 300 码点（600 个 UTF-16 单元）不算超长
    expect(
      reprintErrors({ reason_id: 'R1', comment: '𠀀'.repeat(300) })
    ).toEqual([])
    const ex = await err(
      api.print('missing', { reason_id: 'R1', comment: long }, 'p6')
    )
    for (const lng of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(lng)
      expect(markingErrorMessage(ex)).toBe(
        t('mes.marking.err.commentTooLong', { n: 300 })
      )
    }
  })
  it('同 key 不同内容：422 对象格式 idempotency_key_reused（D57 / D80 补充二）', async () => {
    const r = await api.create({ lot_id: 'lot1' }, 'c1')
    await api.print(r.id, {}, 'k')
    const e = await err(api.print(r.id, { equipment_id: 'X' }, 'k'))
    expect((e as AxiosError).response).toMatchObject({
      status: 422,
      data: { detail: { code: 'idempotency_key_reused' } },
    })
    expect(markingErrorMessage(e)).toBe(
      t('mes.marking.code.idempotency_key_reused')
    )
  })
})

describe('出站 409 check_blocked（marking_inspection）', () => {
  const ctxOf = (e: unknown) =>
    (
      (e as AxiosError).response!.data as {
        detail: { code: string; overridable: boolean; ctx: object }
      }
    ).detail
  it('not_marked（无主记录 / 未首打带 marking_id）→ pending → fail → 放行', async () => {
    const e0 = mockTrackOutMarkingCheck('lot1')
    expect(e0?.response?.status).toBe(409)
    expect(ctxOf(e0)).toMatchObject({
      code: 'check_blocked',
      overridable: false,
      ctx: { check: 'marking_inspection', reason: 'not_marked' },
    })
    expect(ctxOf(e0).ctx).not.toHaveProperty('marking_id')
    const r = await api.create({ lot_id: 'lot1' }, 'c1')
    const e1 = ctxOf(mockTrackOutMarkingCheck('lot1')) as unknown as {
      ctx: object
      results: { ctx: object }[]
    }
    // 未首打：marking_id 有、trace_code 为 null；results[] 打标项同样
    expect(e1).toMatchObject({
      ctx: { reason: 'not_marked', marking_id: r.id, trace_code: null },
    })
    expect(e1.results[0].ctx).toMatchObject({
      check: 'marking_inspection',
      marking_id: r.id,
      trace_code: null,
    })
    await api.print(r.id, {}, 'p1')
    const e2 = ctxOf(mockTrackOutMarkingCheck('lot1')) as unknown as {
      ctx: object
      results: { ctx: object }[]
    }
    expect(e2).toMatchObject({
      ctx: { reason: 'pending', marking_id: r.id, trace_code: r.trace_code },
    })
    expect(e2.results[0].ctx).toMatchObject({
      marking_id: r.id,
      trace_code: r.trace_code,
    })
    await api.inspect(r.id, { result: 'fail', read_code: r.trace_code }, 'i1')
    const ef = mockTrackOutMarkingCheck('lot1')
    expect(ctxOf(ef)).toMatchObject({
      ctx: { reason: 'fail', marking_id: r.id },
    })
    for (const lng of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(lng)
      expect(markingErrorMessage(e0)).toBe(t('mes.marking.checkNotMarked'))
      expect(markingErrorMessage(ef)).toBe(
        t('mes.marking.checkBlocked', { trace: r.trace_code })
      )
    }
    await api.inspect(r.id, { result: 'pass', read_code: r.trace_code }, 'i2')
    expect(mockTrackOutMarkingCheck('lot1')).toBeNull()
  })
  it('pending 文案带追溯码', async () => {
    const r = await api.create({ lot_id: 'lot1' }, 'c1')
    const p = await api.print(r.id, {}, 'p1')
    expect(markingErrorMessage(mockTrackOutMarkingCheck('lot1'))).toBe(
      t('mes.marking.checkPending', { trace: p.trace_code })
    )
  })
})
