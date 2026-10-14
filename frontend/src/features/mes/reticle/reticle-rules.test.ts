import { AxiosHeaders } from 'axios'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { http } from '@/lib/api/client'
import {
  actionBody,
  actionReticle,
  apiError,
  httpReticleApi,
  mockReticleApi,
  resetReticleMock,
} from '@/lib/api/mes/reticle'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import {
  ACTION_LIST,
  actionLabel,
  actionEnabled,
  reticleErrorMessage,
  validateAction,
  validateLocation,
  visibleActions,
} from './reticle-rules'

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
    expect(w).toHaveLength(9)
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
  it('usage 带 Idempotency-Key，其他动作不带', async () => {
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
      undefined
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
    const a = await mockReticleApi.act(
      'r6',
      'inspection',
      { kind: 'particle', result: 'pass' },
      'ik'
    )
    const b = await mockReticleApi.act(
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

describe('mock', () => {
  it('仍挂载时返回 still_mounted；状态不对先 invalid_transition（D71）', async () => {
    // r3：pending_maintenance 且仍挂着
    for (const a of ['restore', 'life-reset', 'repair-complete'] as const)
      await expect(
        mockReticleApi.act('r3', a, { reason: 'x' })
      ).rejects.toMatchObject({
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
    await expect(
      mockReticleApi.act('r2', 'clean-complete', {})
    ).rejects.toMatchObject({
      response: { data: { detail: { code: 'invalid_transition' } } },
    })
  })
  it('超 6 位小数 422 value_error + ctx.max_places', async () => {
    await expect(
      mockReticleApi.act('r1', 'usage', { delta: '1.1234567' })
    ).rejects.toMatchObject({
      response: {
        status: 422,
        data: { detail: [{ code: 'value_error', ctx: { max_places: 6 } }] },
      },
    })
  })
  it('非法迁移；restore 到上限 life_limit_reached；卸载后可 life-reset', async () => {
    await expect(
      mockReticleApi.act('r7', 'hold', { reason: 'x' })
    ).rejects.toMatchObject({
      response: { data: { detail: { code: 'invalid_transition' } } },
    })
    const u = await mockReticleApi.act('r3', 'unmount', {})
    expect(u.data).toMatchObject({ unmount_reason: 'manual' })
    expect((await mockReticleApi.get('r3')).status_code).toBe(
      'pending_maintenance'
    )
    await expect(
      mockReticleApi.act('r3', 'restore', { reason: 'x' })
    ).rejects.toMatchObject({
      response: { data: { detail: { code: 'life_limit_reached' } } },
    })
    const r = await mockReticleApi.act('r3', 'life-reset', { reason: 'pm' })
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
    await mockReticleApi.act('r1', 'usage', { delta: 10 }, 'k')
    const r = await mockReticleApi.act('r1', 'usage', { delta: 10 }, 'k')
    expect(r.reticle?.shot_count).toBe('1210')
    expect((await mockReticleApi.history('r1')).usage).toHaveLength(1)
    const h = await mockReticleApi.act('r2', 'hold', { reason: 'x' })
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
    const p = await mockReticleApi.act('r6', 'inspection', {
      kind: 'particle',
      result: 'pass',
    })
    expect(p.reticle).toMatchObject({
      status_code: 'available',
      inspection_required: false,
    })
    await mockReticleApi.act('r1', 'inspect-start', {})
    const f = await mockReticleApi.act('r1', 'inspection', {
      kind: 'haze',
      result: 'fail',
    })
    expect(f.reticle).toMatchObject({
      status_code: 'on_hold',
      hold_reason: 'inspection_failed',
    })
  })
})
