import { beforeEach, describe, expect, it } from 'vitest'
import {
  mockMarkingApi as api,
  mockTrackOutMarkingCheck,
  resetMarkingMock,
  setMarkingMockTenant,
  setMarkingMockUser,
  setMarkingTplPerms,
  TPL_PERM,
} from './marking'

// B1 打标模板验收要点（p3-tasks「B1→B2→B3 开工清单」）+ TODO-409 对象格式
// D89 补充一、补充二已定
const fail = (p: Promise<unknown>) =>
  p.then(
    () => null,
    (e) => ({ status: e.response.status, detail: e.response.data.detail })
  )
const IN = {
  code: 'B1',
  product_id: 'p3',
  customer_id: 'c1',
  lines: ['{product_code}'],
  date_code_basis: 'marking' as const,
  uses_bin: false,
}
let n = 0
const k = () => `b1-${++n}`
beforeEach(() => resetMarkingMock())

describe('B1 D81 顺序：403 → 缺 key 422 → 请求体 422 → 回放 → 404 → self_approval → 409', () => {
  it('403 先于缺 key', async () => {
    setMarkingTplPerms([TPL_PERM.read])
    const no = undefined as unknown as string
    expect(await fail(api.createTemplate(IN, no))).toMatchObject({
      status: 403,
    })
    expect(
      await fail(api.updateTemplate('t2', { lines: ['{bad}'] }, no))
    ).toMatchObject({ status: 403 })
    expect(await fail(api.newVersion('t2', no))).toMatchObject({ status: 403 })
    // 有 write 没有 approve：审批 403
    setMarkingTplPerms([TPL_PERM.read, TPL_PERM.write])
    expect(await fail(api.approve('t2', no))).toMatchObject({ status: 403 })
    setMarkingTplPerms([])
    expect(await fail(api.templates())).toMatchObject({ status: 403 })
  })
  it('缺 key 422 先于请求体 422；请求体 unknown_placeholder 先于 404', async () => {
    expect(
      await fail(
        api.updateTemplate(
          'nope',
          { lines: ['{bad}'] },
          undefined as unknown as string
        )
      )
    ).toMatchObject({
      status: 422,
      detail: [{ loc: ['header', 'Idempotency-Key'], type: 'missing' }],
    })
    expect(
      await fail(api.updateTemplate('nope', { lines: ['{bad}'] }, k()))
    ).toMatchObject({
      status: 422,
      detail: [
        {
          type: 'value_error',
          ctx: { reason: 'unknown_placeholder', placeholder: 'bad' },
        },
      ],
    })
    expect(
      await fail(api.updateTemplate('nope', { lines: ['{lot_id}'] }, k()))
    ).toMatchObject({
      status: 404,
    })
  })
  it('自批：404 之后、409 之前（非草稿也先报 self_approval）', async () => {
    setMarkingMockUser('eng1')
    expect(await fail(api.approve('nope', k()))).toMatchObject({ status: 404 })
    // t2 已批准、起草人 eng1：先 422 self_approval
    expect(await fail(api.approve('t2', k()))).toMatchObject({
      status: 422,
      detail: [{ ctx: { reason: 'self_approval' } }],
    })
    setMarkingMockUser('qa1')
    expect(await fail(api.approve('t2', k()))).toEqual({
      status: 409,
      detail: { code: 'invalid_transition', message: expect.any(String) },
    })
  })
  it('回放先于 404：成功后同 key 同体原样返回', async () => {
    const key = k()
    const a = await api.createTemplate(IN, key)
    expect(await api.createTemplate(IN, key)).toEqual(a)
  })
})

describe('B1 409 一律对象格式 {code, message}', () => {
  it('D79-2：已有草稿再建新版本 409 draft_exists；非草稿编辑 template_readonly', async () => {
    expect(
      await fail(api.updateTemplate('t2', { lines: ['{lot_id}'] }, k()))
    ).toEqual({
      status: 409,
      detail: { code: 'template_readonly', message: expect.any(String) },
    })
    // 同产品+客户再新建：D89 补充二改为 duplicate（见下）；draft_exists 只在建新版本时
    setMarkingMockUser('eng1')
    await api.newVersion('t2', k())
    expect(await fail(api.newVersion('t2', k()))).toEqual({
      status: 409,
      detail: { code: 'draft_exists', message: expect.any(String) },
    })
  })
  it('D82 补充四例外：出站 check_blocked 保留 results[]（check_type / result / ctx）', () => {
    const e = ['lot1', 'lot2', 'lot3', 'lot4']
      .map((l) => mockTrackOutMarkingCheck(l))
      .find((x) => x != null)!
    const d = e.response!.data as { detail: Record<string, unknown> }
    expect(d.detail).toMatchObject({ code: 'check_blocked' })
    const results = d.detail.results as Record<string, unknown>[]
    expect(Array.isArray(results)).toBe(true)
    expect(results[0]).toMatchObject({
      // D79 补五/七（D89 补充一）
      check_type: 'marking_inspection',
      ctx: expect.objectContaining({
        reason: expect.stringMatching(/^(not_marked|pending|fail)$/),
      }),
    })
  })
})

describe('B1 跨租户 404', () => {
  it('别的租户看不到、改不了、批不了；草稿冲突也按租户隔离', async () => {
    const mine = await api.createTemplate(IN, k())
    setMarkingMockTenant('tenant-b')
    expect(await api.templates()).toEqual([])
    expect(await fail(api.template(mine.id))).toMatchObject({ status: 404 })
    expect(
      await fail(api.updateTemplate(mine.id, { lines: ['{lot_id}'] }, k()))
    ).toMatchObject({
      status: 404,
    })
    setMarkingMockUser('qa1')
    expect(await fail(api.approve(mine.id, k()))).toMatchObject({ status: 404 })
    expect(await fail(api.newVersion('t2', k()))).toMatchObject({ status: 404 })
    // 同产品+客户在 B 租户另建草稿不受 A 的草稿影响
    const theirs = await api.createTemplate(IN, k())
    expect(theirs).toMatchObject({ version: 1, status: 'draft' })
    setMarkingMockTenant('tenant-a')
    expect((await api.templates()).map((x) => x.id)).not.toContain(theirs.id)
  })
})

describe('D89 补充一', () => {
  it('unknown_placeholder 每个一条，loc [body,lines,i]，i 从 0', async () => {
    const r = await fail(
      api.createTemplate(
        { ...IN, lines: ['{product_code}', '{a} {b}', '{c}'] },
        k()
      )
    )
    expect(r?.status).toBe(422)
    expect(r?.detail).toEqual(
      [
        [1, 'a'],
        [1, 'b'],
        [2, 'c'],
      ].map(([i, p]) =>
        expect.objectContaining({
          loc: ['body', 'lines', i],
          type: 'value_error',
          ctx: { reason: 'unknown_placeholder', placeholder: p },
        })
      )
    )
  })
  it('草稿可改；批准新版本后旧 approved 自动 retired；approved/retired 改 409 template_readonly', async () => {
    const d = await api.createTemplate(IN, k())
    const u = await api.updateTemplate(d.id, { lines: ['{lot_id}'] }, k())
    expect(u.lines).toEqual(['{lot_id}'])
    setMarkingMockUser('qa1')
    const a1 = await api.approve(d.id, k())
    expect(a1.status).toBe('approved')
    setMarkingMockUser('eng1')
    const v2 = await api.newVersion(d.id, k())
    expect(v2).toMatchObject({ version: 2, status: 'draft' })
    expect(await fail(api.newVersion(d.id, k()))).toMatchObject({
      status: 409,
      detail: { code: 'draft_exists' },
    })
    setMarkingMockUser('qa1')
    await api.approve(v2.id, k())
    expect((await api.template(d.id)).status).toBe('retired')
    // D90-4：只编辑最新版本；最新为 approved 时 409（不再测编辑 retired）
    expect(
      await fail(api.updateTemplate(v2.id, { lines: ['{lot_id}'] }, k()))
    ).toMatchObject({ status: 409, detail: { code: 'template_readonly' } })
    // D90-3：详情 versions 倒序，未批准为 null
    const det = await api.template(v2.id)
    expect(det.versions?.map((x) => [x.version, x.status])).toEqual([
      [2, 'approved'],
      [1, 'retired'],
    ])
    const v3 = await api.newVersion(v2.id, k())
    const det3 = await api.template(v3.id)
    expect(det3.versions?.[0]).toEqual({
      version: 3,
      status: 'draft',
      created_by: 'qa1',
      created_at: expect.any(String),
      approved_by: null,
      approved_at: null,
    })
    expect(det3.versions?.[1].approved_by).toBe('qa1')
  })
})

const DUP = 'A record with the same key already exists'
describe('D89 补充二 重复键（同 spec.errors.integrity：409 字符串 detail）', () => {
  it('code 大小写不敏感', async () => {
    await api.createTemplate(IN, k())
    expect(
      await fail(
        api.createTemplate({ ...IN, code: 'b1', product_id: 'p2' }, k())
      )
    ).toEqual({ status: 409, detail: DUP })
  })
  it('D90-1：product_id/customer_id 不可改，422 immutable；同值视为没改；404 先于它', async () => {
    const a = await api.createTemplate(IN, k())
    const r = await fail(
      api.updateTemplate(a.id, { product_id: 'p2', customer_id: 'c2' }, k())
    )
    expect(r?.status).toBe(422)
    expect(r?.detail).toEqual(
      ['product_id', 'customer_id'].map((f) =>
        expect.objectContaining({
          loc: ['body', f],
          type: 'value_error',
          ctx: { reason: 'immutable' },
        })
      )
    )
    expect(
      await api.updateTemplate(
        a.id,
        { product_id: a.product_id, customer_id: a.customer_id },
        k()
      )
    ).toMatchObject({ product_id: a.product_id })
    expect(
      await fail(api.updateTemplate('nope', { product_id: 'p2' }, k()))
    ).toMatchObject({ status: 404 })
  })

  it('code 租户内唯一、同产品+客户只一个模板，都 409 duplicate；别的租户不冲突', async () => {
    await api.createTemplate(IN, k())
    expect(
      await fail(api.createTemplate({ ...IN, product_id: 'p2' }, k()))
    ).toMatchObject({ status: 409, detail: DUP })
    expect(
      await fail(api.createTemplate({ ...IN, code: 'B1-other' }, k()))
    ).toMatchObject({ status: 409, detail: DUP })
    setMarkingMockTenant('tenant-b')
    expect(await api.createTemplate(IN, k())).toBeTruthy()
  })
})
