import { AxiosHeaders } from 'axios'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { http } from '@/lib/api/client'
import {
  actionBody,
  bindKey,
  bodySignature,
  actionReticle,
  apiError,
  hasHistory,
  referencedTables,
  httpReticleApi,
  mockReticleApi,
  resetReticleMock,
  D80_KEYED,
  IDEMPOTENT,
  type ReticleAction,
  type ReticleActionInput,
} from '@/lib/api/mes/reticle'
import { OperationKey } from '@/features/mes/common/idem-key'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import {
  ACTION_LIST,
  actionLabel,
  actionEnabled,
  disabledHint,
  reticleErrorMessage,
  validateAction,
  validateLocation,
  visibleActions,
} from './reticle-rules'

let seq = 0
/** 测试里每次调用默认带一个新 key（D80）。 */
const act = (...[id, a, input, key]: Parameters<typeof mockReticleApi.act>) =>
  mockReticleApi.act(id, a, input, key ?? `t-${++seq}`)

beforeEach(() => resetReticleMock())
afterEach(() => {
  vi.restoreAllMocks()
  void i18n.changeLanguage('zh-CN')
})

describe('权限', () => {
  it('restore / scrap / life-reset 只看 override', () => {
    const only = (p: string[]) => visibleActions((x) => p.includes(x))
    expect(only([MES_PERM.reticleOverride]).sort()).toEqual(
      ['life-reset', 'restore', 'scrap'].sort()
    )
    const w = only([MES_PERM.reticleWrite])
    expect(w).not.toContain('scrap')
    expect(w).toContain('usage')
    expect(w).toHaveLength(11)
    expect(only([])).toEqual([])
  })
  it('scrapped 终态所有动作都不可用', () => {
    for (const a of ACTION_LIST)
      expect(actionEnabled({ status_code: 'scrapped' }, a)).toBe(false)
    expect(actionEnabled({ status_code: 'on_hold' }, 'release')).toBe(true)
    expect(actionEnabled({ status_code: 'on_hold' }, 'hold')).toBe(false)
  })
})

describe('请求体白名单', () => {
  it('只发模型字段，hold_reason / status_code 只读不发', () => {
    const dirty = {
      reason: 'x',
      comment: 'c',
      hold_reason: 'manual',
      status_code: 'available',
      delta: 1,
    } as never
    expect(actionBody('hold', dirty)).toEqual({ reason: 'x' })
    expect(actionBody('release', dirty)).toEqual({ comment: 'c' })
    expect(actionBody('usage', dirty)).toEqual({ delta: 1 })
    expect(
      actionBody('usage', { delta: -1, reason_id: '', note: ' ' })
    ).toEqual({ delta: -1 })
  })
  it('D80 动作带 Idempotency-Key，清洗等其他动作不带', async () => {
    const post = vi.spyOn(http, 'post').mockResolvedValue({ data: {} })
    await httpReticleApi.act('r1', 'usage', { delta: 5, reason: 'x' }, 'k1')
    expect(post).toHaveBeenCalledWith(
      '/mes/reticle/r1/usage',
      { delta: 5 },
      { headers: { 'Idempotency-Key': 'k1' } }
    )
    await httpReticleApi.act('r1', 'life-reset', { reason: 'r' }, 'k2')
    expect(post).toHaveBeenLastCalledWith(
      '/mes/reticle/r1/life-reset',
      { reason: 'r' },
      { headers: { 'Idempotency-Key': 'k2' } }
    )
    await httpReticleApi.act('r1', 'clean-start', { comment: 'c' }, 'k3')
    expect(post).toHaveBeenLastCalledWith(
      '/mes/reticle/r1/clean-start',
      { comment: 'c' },
      { headers: { 'Idempotency-Key': 'k3' } }
    )
    void AxiosHeaders
  })
})

describe('表单校验', () => {
  it('负 delta 必须 reason_id；0 不行；小数最多 6 位', () => {
    expect(validateAction('usage', { delta: '-5' }).reason_id).toBeTruthy()
    expect(validateAction('usage', { delta: '-5', reason_id: 'R1' })).toEqual(
      {}
    )
    expect(validateAction('usage', { delta: '0' }).delta).toBeTruthy()
    expect(validateAction('usage', { delta: '1.1234567' }).delta).toBe(
      t('mes.reticle.err.maxPlaces', { max: 6 })
    )
  })
  it('reason 必填且 ≤300，comment/note ≤300，库位 ≤64', () => {
    expect(validateAction('scrap', {}).reason).toBeTruthy()
    expect(
      validateAction('scrap', { reason: 'a'.repeat(301) }).reason
    ).toBeTruthy()
    expect(validateAction('scrap', { reason: 'a'.repeat(300) })).toEqual({})
    expect(
      validateAction('release', { comment: 'a'.repeat(301) }).comment
    ).toBeTruthy()
    expect(validateAction('release', {})).toEqual({})
    expect(
      validateAction('usage', { delta: '1', note: 'a'.repeat(301) }).note
    ).toBeTruthy()
    expect(validateLocation('a'.repeat(64))).toBeNull()
    expect(validateLocation('a'.repeat(65))).toBeTruthy()
  })
})

describe('409 错误码三语', () => {
  const codes = [
    'invalid_transition',
    'life_limit_reached',
    'already_mounted',
    'still_mounted',
  ]
  it.each(['zh-CN', 'en', 'ja'])('%s 有友好提示且不露出码名', async (l) => {
    await i18n.changeLanguage(l)
    for (const c of codes) {
      const m = reticleErrorMessage(apiError(409, { code: c }), 'restore')
      expect(m).not.toContain(c)
      expect(m.length).toBeGreaterThan(5)
    }
    expect(
      reticleErrorMessage(
        apiError(409, { code: 'still_mounted' }),
        'clean-start'
      )
    ).toContain(t('mes.reticle.action.clean-start'))
  })
})

describe('对齐 B4 接口', () => {
  it('列表 page_size ≤100；历史合并列表按 type 分组', async () => {
    const get = vi.spyOn(http, 'get').mockImplementation(((url: string) =>
      Promise.resolve({
        data: url.endsWith('/history')
          ? {
              data: [
                {
                  type: 'status',
                  at: 'z',
                  username: 'u',
                  action: 'life_reset',
                },
                { type: 'usage', at: 'z' },
                { type: 'mount', at: 'z' },
                { type: 'inspection', at: 'z' },
                { type: 'incident', at: 'z' },
              ],
              count: 5,
            }
          : { data: [], count: 0 },
      })) as never)
    await httpReticleApi.list()
    expect(get).toHaveBeenCalledWith('/mes/reticle', {
      params: { page_size: 100 },
    })
    const h = await httpReticleApi.history('r1')
    expect(get).toHaveBeenLastCalledWith('/mes/reticle/r1/history', {
      params: { page_size: 200 },
    })
    expect(h.status_log[0]).toMatchObject({ username: 'u', at: 'z' })
    expect([h.usage, h.mounts, h.inspections].map((x) => x.length)).toEqual([
      1, 1, 1,
    ])
  })
  it('动作响应取光罩行：usage/inspection 取 reticle，unmount 无', () => {
    const r = { id: 'r' } as never
    expect(actionReticle('hold', { data: r })).toBe(r)
    expect(actionReticle('usage', { data: {}, reticle: r })).toBe(r)
    expect(actionReticle('unmount', { data: {} })).toBeNull()
  })
  it('履历 action 枚举（下划线）显示为动作名', () => {
    expect(actionLabel('life_reset')).toBe(t('mes.reticle.action.life-reset'))
    expect(actionLabel('system')).toBe(t('mes.reticle.system'))
    expect(actionLabel('mount')).toBe(t('mes.reticle.action.mount'))
  })
  it('检查与卸载请求体白名单', () => {
    expect(
      actionBody('inspection', {
        kind: 'particle',
        result: 'fail',
        reason: 'x',
        defect_count: 2,
      })
    ).toEqual({ kind: 'particle', result: 'fail', defect_count: 2 })
    expect(actionBody('unmount', { comment: 'c', reason: 'x' })).toEqual({
      comment: 'c',
    })
    expect(validateAction('inspection', {}).result).toBeTruthy()
    expect(
      actionEnabled({ status_code: 'available', equipment_id: null }, 'unmount')
    ).toBe(false)
  })
  it('422 value_error 带 ctx.max_places 时提示小数位上限', () => {
    const m = reticleErrorMessage(
      apiError(422, [
        {
          loc: ['body', 'delta'],
          type: 'value_error',
          msg: 'x',
          ctx: { max_places: 6 },
        },
      ])
    )
    expect(m).toBe(t('mes.reticle.err.maxPlaces', { max: 6 }))
  })
})

describe('检查录入 D57（D71 补充）', () => {
  it('inspection 带 Idempotency-Key', async () => {
    const post = vi.spyOn(http, 'post').mockResolvedValue({ data: {} })
    await httpReticleApi.act(
      'r1',
      'inspection',
      { kind: 'cd', result: 'pass', disposition: 'none' },
      'k9'
    )
    expect(post).toHaveBeenCalledWith(
      '/mes/reticle/r1/inspection',
      { kind: 'cd', result: 'pass', disposition: 'none' },
      { headers: { 'Idempotency-Key': 'k9' } }
    )
  })
  it('mock 同 key 重放不重复写检查记录；不传 disposition 默认 none', async () => {
    const a = await act(
      'r6',
      'inspection',
      { kind: 'particle', result: 'pass' },
      'ik'
    )
    const b = await act(
      'r6',
      'inspection',
      { kind: 'particle', result: 'pass' },
      'ik'
    )
    expect(b).toEqual(a)
    expect(a.data).toMatchObject({ disposition: 'none' })
    expect((await mockReticleApi.history('r6')).inspections).toHaveLength(2)
  })
})

describe('幂等键绑定请求体（H-1）', () => {
  it('内容不变复用 key，内容变了换新 key；白名单外字段不影响', () => {
    let n = 0
    const gen = () => `k${++n}`
    const a = bindKey(null, bodySignature('usage', { delta: '5' }), gen)
    const b = bindKey(
      a,
      bodySignature('usage', { delta: '5', reason: 'ignored' }),
      gen
    )
    expect(b.key).toBe(a.key)
    const c = bindKey(b, bodySignature('usage', { delta: '6' }), gen)
    expect(c.key).not.toBe(a.key)
    expect(bodySignature('usage', { note: 'n', delta: 1 })).toBe(
      bodySignature('usage', { delta: 1, note: 'n' })
    )
  })
  it('mock 同 key 不同内容 422 idempotency_key_reused（D57/D80），三语文案', async () => {
    await act('r1', 'usage', { delta: 1 }, 'same')
    const err = await mockReticleApi
      .act('r1', 'usage', { delta: 2 }, 'same')
      .catch((e: unknown) => e)
    expect(err).toMatchObject({
      response: {
        status: 422,
        data: { detail: { code: 'idempotency_key_reused' } },
      },
    })
    for (const l of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(l)
      expect(reticleErrorMessage(err, 'usage')).toBe(
        t('mes.reticle.err.keyReused')
      )
    }
  })
  it('409 idempotency_in_progress 三语提示；内容不变重试复用同 key', async () => {
    const err = apiError(409, { code: 'idempotency_in_progress' })
    for (const l of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(l)
      const m = reticleErrorMessage(err, 'inspection')
      expect(m).toBe(t('mes.reticle.code.idempotency_in_progress'))
      expect(m).not.toContain('idempotency')
    }
    const sig = bodySignature('inspection', { kind: 'cd', result: 'pass' })
    const first = bindKey(null, sig, () => 'k1')
    expect(bindKey(first, sig, () => 'k2').key).toBe('k1')
  })
})

describe('mock', () => {
  it('仍挂载时返回 still_mounted；状态不对先 invalid_transition（D71）', async () => {
    // r3：pending_maintenance 且仍挂着
    for (const a of ['restore', 'life-reset', 'repair-complete'] as const)
      await expect(act('r3', a, { reason: 'x' })).rejects.toMatchObject({
        response: {
          status: 409,
          data: {
            detail: {
              code: 'still_mounted',
              status_code: 'pending_maintenance',
            },
          },
        },
      })
    // r2 在用且挂着：inspect-start 状态不允许 → invalid_transition 优先
    await expect(act('r2', 'clean-complete', {})).rejects.toMatchObject({
      response: { data: { detail: { code: 'invalid_transition' } } },
    })
  })
  it('超 6 位小数 422 value_error + ctx.max_places', async () => {
    await expect(
      act('r1', 'usage', { delta: '1.1234567' })
    ).rejects.toMatchObject({
      response: {
        status: 422,
        data: { detail: [{ code: 'value_error', ctx: { max_places: 6 } }] },
      },
    })
  })
  it('非法迁移；restore 到上限 life_limit_reached；卸载后可 life-reset', async () => {
    await expect(act('r7', 'hold', { reason: 'x' })).rejects.toMatchObject({
      response: { data: { detail: { code: 'invalid_transition' } } },
    })
    const u = await act('r3', 'unmount', {})
    expect(u.data).toMatchObject({ unmount_reason: 'manual' })
    expect((await mockReticleApi.get('r3')).status_code).toBe(
      'pending_maintenance'
    )
    await expect(act('r3', 'restore', { reason: 'x' })).rejects.toMatchObject({
      response: { data: { detail: { code: 'life_limit_reached' } } },
    })
    const r = await act('r3', 'life-reset', { reason: 'pm' })
    expect(r.data).toMatchObject({ status_code: 'available', shot_count: '0' })
    expect(r.usage).toMatchObject({
      kind: 'reset',
      comment: 'pm',
      reason_id: null,
    })
    const h = await mockReticleApi.history('r3')
    expect(h.status_log[0]).toMatchObject({ action: 'life_reset' })
  })
  it('usage 同 key 重放不重复计数；在用 hold 记 available 并卸载', async () => {
    await act('r1', 'usage', { delta: 10 }, 'k')
    const r = await act('r1', 'usage', { delta: 10 }, 'k')
    expect(r.reticle?.shot_count).toBe('1210')
    expect((await mockReticleApi.history('r1')).usage).toHaveLength(1)
    const h = await act('r2', 'hold', { reason: 'x' })
    expect(h.data).toMatchObject({
      status_code: 'on_hold',
      hold_reason: 'manual',
      status_before_hold: 'available',
      equipment_id: null,
    })
    const s = (await mockReticleApi.history('r2')).status_log[0]
    expect(s).toMatchObject({
      from_status: 'in_use',
      to_status: 'on_hold',
      reason: 'x',
      username: 'me',
    })
  })
  it('检查：inspecting pass → available；fail → on_hold(inspection_failed)', async () => {
    const p = await act('r6', 'inspection', {
      kind: 'particle',
      result: 'pass',
    })
    expect(p.reticle).toMatchObject({
      status_code: 'available',
      inspection_required: false,
    })
    await act('r1', 'inspect-start', {})
    const f = await act('r1', 'inspection', {
      kind: 'haze',
      result: 'fail',
    })
    expect(f.reticle).toMatchObject({
      status_code: 'on_hold',
      hold_reason: 'inspection_failed',
    })
  })
})

describe('D72', () => {
  beforeEach(() => resetReticleMock())
  afterEach(() => vi.restoreAllMocks())
  it('scrapped 拒绝 usage / 检查录入 → 409 invalid_transition，按钮禁用并有提示', async () => {
    for (const [a, input] of [
      ['usage', { delta: 1 }],
      ['inspection', { kind: 'cd', result: 'fail' }],
    ] as const) {
      const err = await mockReticleApi
        .act('r7', a, input, `k-${a}`)
        .catch((e: unknown) => e)
      expect(err).toMatchObject({
        response: {
          status: 409,
          data: { detail: { code: 'invalid_transition' } },
        },
      })
      expect(actionEnabled({ status_code: 'scrapped' }, a)).toBe(false)
      expect(reticleErrorMessage(err, a)).toBe(
        t('mes.reticle.code.invalid_transition', { action: actionLabel(a) })
      )
    }
    expect(disabledHint({ status_code: 'scrapped' })).toBe(
      t('mes.reticle.scrappedHint')
    )
    expect(disabledHint({ status_code: 'available' })).toBeUndefined()
  })
  it('有履历删除 → 409 referenced 三语；无履历可删', async () => {
    const err = await mockReticleApi.remove('r6').catch((e: unknown) => e)
    expect(err).toMatchObject({
      response: {
        status: 409,
        data: {
          detail: {
            code: 'referenced',
            message: expect.any(String),
            tables: referencedTables(await mockReticleApi.history('r6')),
          },
        },
      },
    })
    expect(referencedTables(await mockReticleApi.history('r6'))).not.toEqual([])
    for (const l of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(l)
      const m = reticleErrorMessage(err)
      expect(m).toBe(t('mes.reticle.code.referenced'))
      expect(m).not.toContain('referenced')
    }
    await i18n.changeLanguage('zh-CN')
    const h = await mockReticleApi.history('r1')
    expect(hasHistory(h)).toBe(false)
    await mockReticleApi.remove('r1')
    expect((await mockReticleApi.list()).some((x) => x.id === 'r1')).toBe(false)
  })
  it('referenced 的 tables 只列有记录的履历表', () => {
    const e = { status_log: [], usage: [], mounts: [], inspections: [] }
    expect(referencedTables(e)).toEqual([])
    expect(
      referencedTables({ ...e, usage: [{}], inspections: [{}] } as never)
    ).toEqual(['mes_reticle_usage', 'mes_reticle_inspection'])
  })
  it('http 删除走 DELETE /mes/reticle/{id}', async () => {
    const spy = vi
      .spyOn(http, 'delete')
      .mockResolvedValue({ data: null, status: 204 })
    await httpReticleApi.remove('r9')
    expect(spy).toHaveBeenCalledWith('/mes/reticle/r9')
  })
  it('源码与三语里没有 idempotency_key_mismatch', async () => {
    const files = import.meta.glob(
      ['/src/**/*.{ts,tsx,json}', '!/src/**/*.test.*'],
      { query: '?raw', import: 'default', eager: true }
    ) as Record<string, string>
    const bad = Object.entries(files)
      .filter(([, c]) => c.includes('idempotency_key_' + 'mismatch'))
      .map(([f]) => f)
    expect(bad).toEqual([])
  })
})

describe('D80 + 补充二：/mes/reticle 14 个手工写接口必填 Idempotency-Key', () => {
  const BODY: Partial<Record<ReticleAction, ReticleActionInput>> = {
    usage: { delta: 1 },
    inspection: { kind: 'cd', result: 'pass', disposition: 'none' },
    unmount: {},
    hold: { reason: 'x' },
    release: { comment: 'c' },
    restore: { reason: 'x' },
    'life-reset': { reason: 'x' },
    scrap: { reason: 'x' },
    mount: { equipment_id: 'e9' },
    incident: { kind: 'drop' },
    'clean-start': {},
    'clean-complete': {},
    'repair-complete': {},
    'inspect-start': {},
  }
  it('清单为 14 个，全部在 IDEMPOTENT 里', () => {
    expect([...D80_KEYED].sort()).toEqual(
      [
        'usage',
        'incident',
        'inspection',
        'mount',
        'unmount',
        'hold',
        'release',
        'restore',
        'life-reset',
        'scrap',
        'clean-start',
        'clean-complete',
        'repair-complete',
        'inspect-start',
      ].sort()
    )
    expect(D80_KEYED).toHaveLength(14)
    expect([...IDEMPOTENT].sort()).toEqual(Object.keys(BODY).sort())
  })
  it('http：14 个动作都带 Idempotency-Key 头', async () => {
    const post = vi.spyOn(http, 'post').mockResolvedValue({ data: {} })
    for (const a of IDEMPOTENT) {
      await httpReticleApi.act('r1', a, BODY[a]!, `key-${a}`)
      expect(post).toHaveBeenLastCalledWith(
        `/mes/reticle/r1/${a}`,
        expect.anything(),
        { headers: { 'Idempotency-Key': `key-${a}` } }
      )
    }
    expect(post).toHaveBeenCalledTimes(IDEMPOTENT.length)
  })
  it('mock：缺 key 一律 422 missing（loc header），三语文案', async () => {
    for (const a of IDEMPOTENT) {
      const err = await mockReticleApi
        .act('r1', a, BODY[a]!)
        .catch((e: unknown) => e)
      expect(err).toMatchObject({
        response: {
          status: 422,
          data: {
            detail: [{ type: 'missing', loc: ['header', 'Idempotency-Key'] }],
          },
        },
      })
    }
    const err = await mockReticleApi
      .act('r1', 'scrap', { reason: 'x' })
      .catch((e: unknown) => e)
    for (const l of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(l)
      const m = reticleErrorMessage(err, 'scrap')
      expect(m).toBe(t('mes.reticle.err.keyMissing'))
      expect(m).not.toBe('mes.reticle.err.keyMissing')
    }
  })
  it('mock：同 key 重放返回原响应，不重复写；换请求体 422 reused', async () => {
    const a = await act('r1', 'hold', { reason: 'x' }, 'hk')
    const b = await act('r1', 'hold', { reason: 'x' }, 'hk')
    expect(b).toEqual(a)
    expect(
      (await mockReticleApi.history('r1')).status_log.filter(
        (x) => x.action === 'hold'
      )
    ).toHaveLength(1)
    await expect(
      act('r1', 'hold', { reason: 'y' }, 'hk')
    ).rejects.toMatchObject({
      response: {
        status: 422,
        data: { detail: { code: 'idempotency_key_reused' } },
      },
    })
  })
})

describe('OperationKey：一次操作一个 key', () => {
  it('重试沿用；请求体变或成功后换新 key', () => {
    let n = 0
    const k = new OperationKey(() => `k${++n}`)
    const s1 = bodySignature('hold', { reason: 'a' })
    const s2 = bodySignature('hold', { reason: 'b' })
    expect(k.key(s1)).toBe('k1')
    expect(k.key(s1)).toBe('k1')
    expect(k.key(s2)).toBe('k2')
    k.done()
    expect(k.key(s2)).toBe('k3')
  })
})

describe('D80 补充二：上机 / 登记异常对话框的接口与 mock', () => {
  it('http 请求体按 MountIn / IncidentIn 白名单', async () => {
    const post = vi.spyOn(http, 'post').mockResolvedValue({ data: {} })
    await httpReticleApi.act(
      'r1',
      'mount',
      { equipment_id: 'e9', slot_code: 'S1', comment: 'c', reason: 'x' },
      'km'
    )
    expect(post).toHaveBeenLastCalledWith(
      '/mes/reticle/r1/mount',
      { equipment_id: 'e9', slot_code: 'S1', comment: 'c' },
      { headers: { 'Idempotency-Key': 'km' } }
    )
    await httpReticleApi.act(
      'r1',
      'incident',
      { kind: 'drop', lot_id: 'L1', description: 'd', comment: 'x' },
      'ki'
    )
    expect(post).toHaveBeenLastCalledWith(
      '/mes/reticle/r1/incident',
      { kind: 'drop', lot_id: 'L1', description: 'd' },
      { headers: { 'Idempotency-Key': 'ki' } }
    )
  })
  it('权限：两者都要 mes.reticle:write；mount 仅 available 且未挂载', () => {
    expect(visibleActions((p) => p === MES_PERM.reticleWrite)).toEqual(
      expect.arrayContaining(['mount', 'incident'])
    )
    expect(visibleActions(() => false)).not.toContain('mount')
    expect(
      actionEnabled({ status_code: 'available', equipment_id: null }, 'mount')
    ).toBe(true)
    expect(
      actionEnabled({ status_code: 'available', equipment_id: 'e1' }, 'mount')
    ).toBe(false)
    expect(
      actionEnabled({ status_code: 'dirty', equipment_id: null }, 'mount')
    ).toBe(false)
    expect(actionEnabled({ status_code: 'scrapped' }, 'incident')).toBe(false)
    expect(actionEnabled({ status_code: 'on_hold' }, 'incident')).toBe(true)
  })
  it('表单校验：mount 机台必填、槽位 ≤64；incident 类型必填、描述 ≤300', () => {
    expect(validateAction('mount', {})).toHaveProperty('equipment_id')
    expect(
      validateAction('mount', { equipment_id: 'e', slot_code: 'x'.repeat(65) })
    ).toHaveProperty('slot_code')
    expect(validateAction('incident', {})).toHaveProperty('kind')
    expect(
      validateAction('incident', { kind: 'drop', description: 'x'.repeat(301) })
    ).toHaveProperty('description')
    expect(validateAction('incident', { kind: 'other' })).toEqual({})
  })
  it('mock mount：available → in_use 并记挂载；重复 409 already_mounted；同 key 重放', async () => {
    const a = await act(
      'r1',
      'mount',
      { equipment_id: 'e9', slot_code: 'S1' },
      'mk'
    )
    expect(a.data).toMatchObject({
      equipment_id: 'e9',
      slot_code: 'S1',
      unmounted_at: null,
    })
    expect(
      await act('r1', 'mount', { equipment_id: 'e9', slot_code: 'S1' }, 'mk')
    ).toEqual(a)
    expect(await mockReticleApi.get('r1')).toMatchObject({
      status_code: 'in_use',
      equipment_id: 'e9',
      mount_count: 1,
    })
    expect(
      (await mockReticleApi.history('r1')).mounts.filter(
        (m) => m.unmounted_at == null
      )
    ).toHaveLength(1)
    await expect(
      act('r1', 'mount', { equipment_id: 'e8' })
    ).rejects.toMatchObject({
      response: { status: 409, data: { detail: { code: 'already_mounted' } } },
    })
  })
  it('mock incident：转 on_hold(incident) + 待检；scrapped 409', async () => {
    const r = await act('r1', 'incident', {
      kind: 'collision',
      description: 'd',
    })
    expect(r.data).toMatchObject({
      kind: 'collision',
      description: 'd',
      source: 'manual',
    })
    expect(r.reticle).toMatchObject({
      status_code: 'on_hold',
      hold_reason: 'incident',
      inspection_required: true,
    })
    await act('r1', 'scrap', { reason: 'x' })
    await expect(act('r1', 'incident', { kind: 'drop' })).rejects.toMatchObject(
      {
        response: {
          status: 409,
          data: { detail: { code: 'invalid_transition' } },
        },
      }
    )
  })
  it('reused 两种格式都识别；slot_occupied 三语', async () => {
    const arr = apiError(422, [
      { loc: ['header', 'Idempotency-Key'], type: 'idempotency_key_reused' },
    ])
    const obj = apiError(422, { code: 'idempotency_key_reused', message: 'x' })
    for (const l of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(l)
      expect(reticleErrorMessage(arr)).toBe(t('mes.reticle.err.keyReused'))
      expect(reticleErrorMessage(obj)).toBe(t('mes.reticle.err.keyReused'))
      expect(
        reticleErrorMessage(apiError(409, { code: 'slot_occupied' }), 'mount')
      ).toBe(t('mes.reticle.code.slot_occupied'))
      expect(t('mes.reticle.incidentKind.drop')).not.toContain('incidentKind')
    }
  })
})

describe('N-E2：光罩 mock 校验顺序', () => {
  it('缺 key 422 → body 422 → 重放 → 409', async () => {
    // r7 为 scrapped：状态校验 409
    await expect(
      mockReticleApi.act('r7', 'usage', { delta: 0 })
    ).rejects.toMatchObject({
      response: { status: 422, data: { detail: [{ type: 'missing' }] } },
    })
    await expect(act('r7', 'usage', { delta: 0 }, 'o1')).rejects.toMatchObject({
      response: { status: 422 },
    })
    await expect(act('r7', 'mount', {}, 'o2')).rejects.toMatchObject({
      response: { status: 422 },
    })
    await expect(act('r7', 'usage', { delta: 1 }, 'o3')).rejects.toMatchObject({
      response: { status: 409 },
    })
    // 重放先于 409：r1 hold 成功后再 hold 同 key 返回原响应
    const h = await act('r1', 'hold', { reason: 'x' }, 'o4')
    expect(await act('r1', 'hold', { reason: 'x' }, 'o4')).toEqual(h)
    await expect(
      act('r1', 'hold', { reason: 'x' }, 'o5')
    ).rejects.toMatchObject({
      response: { status: 409 },
    })
  })
})
