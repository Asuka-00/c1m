import { describe, expect, it } from 'vitest'
import { formSchema } from './login-schema'

describe('login form', () => {
  it('accepts usernames only', () => {
    const ok = (login: string) =>
      formSchema.safeParse({ login, password: 'x' }).success
    expect(ok('admin')).toBe(true)
    expect(ok('Li.Si_01')).toBe(true)
    expect(ok('admin@example.com')).toBe(false)
    expect(ok('ab')).toBe(false)
  })
})
