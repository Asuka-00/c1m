import { AxiosHeaders } from 'axios'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { http } from '@/lib/api/client'
import {
  actionBody,
  apiError,
  httpReticleApi,
  mockReticleApi,
  resetReticleMock,
} from '@/lib/api/mes/reticle'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import {
  ACTION_LIST,
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
    expect(w).toHaveLength(7)
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
      t('mes.err.code.too_many_decimals')
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

describe('mock', () => {
  it('仍挂载时五个动作返回 still_mounted', async () => {
    // r3：pending_maintenance 且仍挂着
    for (const a of ['restore', 'life-reset', 'repair-complete'] as const)
      await expect(
        mockReticleApi.act('r3', a, { reason: 'x' })
      ).rejects.toMatchObject({
        response: { status: 409, data: { detail: { code: 'still_mounted' } } },
      })
  })
  it('非法迁移 invalid_transition；restore 到上限 life_limit_reached', async () => {
    await expect(
      mockReticleApi.act('r7', 'hold', { reason: 'x' })
    ).rejects.toMatchObject({
      response: { data: { detail: { code: 'invalid_transition' } } },
    })
    // 先 hold 卸载 r3，再 release 回 status_before_hold，restore 达上限
    await mockReticleApi.act('r3', 'hold', { reason: 'x' })
    await mockReticleApi.act('r3', 'release', {})
    await expect(
      mockReticleApi.act('r3', 'restore', { reason: 'x' })
    ).rejects.toMatchObject({
      response: { data: { detail: { code: 'life_limit_reached' } } },
    })
    const r = await mockReticleApi.act('r3', 'life-reset', { reason: 'pm' })
    expect(r.status_code).toBe('available')
    expect(r.shot_count).toBe('0')
    const h = await mockReticleApi.history('r3')
    expect(h.usage[0]).toMatchObject({
      kind: 'reset',
      comment: 'pm',
      reason_id: null,
    })
  })
  it('usage 同 key 重放不重复计数；在用 hold 记 available 并卸载', async () => {
    await mockReticleApi.act('r1', 'usage', { delta: 10 }, 'k')
    const r = await mockReticleApi.act('r1', 'usage', { delta: 10 }, 'k')
    expect(r.shot_count).toBe('1210')
    expect((await mockReticleApi.history('r1')).usage).toHaveLength(1)
    const h = await mockReticleApi.act('r2', 'hold', { reason: 'x' })
    expect(h).toMatchObject({
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
    })
  })
})
