import { describe, expect, it } from 'vitest'
import en from './locales/en.json'
import ja from './locales/ja.json'
import mesEn from './locales/mes/en.json'
import mesJa from './locales/mes/ja.json'
import mesZh from './locales/mes/zh-CN.json'
import zh from './locales/zh-CN.json'
import { isPlatformOnly, tenantWordingLeaks } from './workspace-wording'

describe('workspace wording', () => {
  it.each([
    ['zh-CN', zh],
    ['en', en],
    ['ja', ja],
    ['mes/zh-CN', mesZh],
    ['mes/en', mesEn],
    ['mes/ja', mesJa],
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
