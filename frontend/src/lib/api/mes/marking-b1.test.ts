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
// 未定项（B1_PENDING：请求体字段名、unknown_placeholder loc、版本/状态字段名、草稿编辑、重打 missing 条数、check_blocked result）不断言
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
    await api.createTemplate(IN, k())
    expect(await fail(api.createTemplate({ ...IN, code: 'B1b' }, k()))).toEqual(
      {
        status: 409,
        detail: { code: 'draft_exists', message: expect.any(String) },
      }
    )
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
      check_type: expect.any(String),
      // result 取值未定（TODO B1-6），只断言字段存在
      result: expect.anything(),
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
    // 版本号字段名未定（TODO B1-3），只断言建成功
    const theirs = await api.createTemplate(IN, k())
    setMarkingMockTenant('tenant-a')
    expect((await api.templates()).map((x) => x.id)).not.toContain(theirs.id)
  })
})
