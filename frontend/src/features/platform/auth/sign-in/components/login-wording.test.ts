import en from '@/i18n/locales/en.json'
import ja from '@/i18n/locales/ja.json'
import zh from '@/i18n/locales/zh-CN.json'
import { describe, expect, it } from 'vitest'

describe('AUTH-01 登录框文案', () => {
  it('三语提示都只写「用户名」，不再提邮箱', () => {
    expect(zh.auth.loginPlaceholder).toBe('用户名')
    expect(en.auth.loginPlaceholder).toBe('Username')
    expect(ja.auth.loginPlaceholder).toBe('ユーザー名')
    for (const l of [zh, en, ja]) {
      expect(l.auth.loginLabel).toBe(l.auth.loginPlaceholder)
      expect(l.auth.loginRequired).not.toMatch(/邮箱|email|メール/i)
    }
  })
})
