import { describe, expect, it } from 'vitest'
import { isPlatformPath } from './space'

describe('isPlatformPath', () => {
  it('matches the platform console and its pages', () => {
    expect(isPlatformPath('/platform')).toBe(true)
    expect(isPlatformPath('/platform/tenants')).toBe(true)
    expect(isPlatformPath('/platform/login-log')).toBe(true)
  })
  it('does not match workspace paths', () => {
    expect(isPlatformPath('/')).toBe(false)
    expect(isPlatformPath('/platforms')).toBe(false)
    expect(isPlatformPath('/members')).toBe(false)
    expect(isPlatformPath('/mes/platform')).toBe(false)
  })
})
