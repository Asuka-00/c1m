import { en, ja, zh } from '@/test-utils/locales'
import { describe, expect, it } from 'vitest'
import { isPlatformOnly, tenantWordingLeaks } from './workspace-wording'

describe('workspace wording', () => {
  it.each([
    ['zh-CN', zh],
    ['en', en],
    ['ja', ja],
  ])('%s has no tenant wording outside the platform console', (_, b) => {
    expect(tenantWordingLeaks(b)).toEqual([])
  })
  it('flags workspace keys and allows platform keys', () => {
    expect(tenantWordingLeaks({ members: { desc: '租户成员' } })).toHaveLength(
      1
    )
    expect(tenantWordingLeaks({ platform: { x: 'Tenant' } })).toEqual([])
    expect(isPlatformOnly('menu.p-tenants')).toBe(true)
    expect(isPlatformOnly('menu.members')).toBe(false)
  })
})
