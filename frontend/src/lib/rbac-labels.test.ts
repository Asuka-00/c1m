import i18n from '@/i18n'
import { describe, expect, it } from 'vitest'
import {
  permKey,
  permLabel,
  roleLabel,
  permDesc,
  pickLangSegment,
  roleDesc,
} from './rbac-labels'

describe('内置权限 / 角色名称', () => {
  it('编码转换为 i18n 键', () => {
    expect(permKey('mes.lot:start')).toBe('permName.mes_lot__start')
  })
  it('内置说明按语言翻译，自定义说明保留', async () => {
    await i18n.changeLanguage('zh-CN')
    expect(
      roleDesc(
        { name: 'member', description: 'Read-only access to business data' },
        false
      )
    ).toBe('只读访问业务数据')
    expect(
      roleDesc(
        {
          name: 'admin',
          description: 'Platform administrator with all permissions',
        },
        true
      )
    ).toBe('拥有全部权限的平台管理员')
    expect(roleDesc({ name: 'member', description: '自定义' }, false)).toBe(
      '自定义'
    )
    expect(permDesc('members:read', 'Allows: View users')).toBe(
      '允许：查看用户'
    )
    expect(permDesc('members:read', '自定义')).toBe('自定义')
  })
  it('内置英文名按语言翻译，自定义名保留', async () => {
    await i18n.changeLanguage('zh-CN')
    expect(permLabel('users:read', 'View platform users')).toBe('查看平台用户')
    expect(permLabel('users:read', null)).toBe('查看平台用户')
    expect(permLabel('users:read', '自定义')).toBe('自定义')
    expect(permLabel('x:y', null)).toBe('x:y')
    expect(roleLabel({ name: 'owner', title: 'System admin' })).toBe(
      '系统管理员'
    )
    expect(permLabel('members:read', 'View users')).toBe('查看用户')
    expect(roleLabel({ name: 'qa', title: '质检' })).toBe('质检')
    await i18n.changeLanguage('ja')
    expect(roleLabel({ name: 'member', title: null })).toBe('一般ユーザー')
  })
})

describe('三语权限说明（en|zh|ja）', () => {
  const raw = 'View users|查看用户|ユーザーを表示'
  it('有前端文案时用文案，不显示原始串', async () => {
    await i18n.changeLanguage('zh-CN')
    const v = permDesc('members:read', raw)
    expect(v).toBe(i18n.t('permDesc.members__read'))
    expect(v).not.toContain('|')
  })
  it('无文案时按语言取段，缺失回退 en', async () => {
    await i18n.changeLanguage('zh-CN')
    expect(permDesc('x.unknown:perm', raw)).toBe('查看用户')
    await i18n.changeLanguage('ja')
    expect(permDesc('x.unknown:perm', raw)).toBe('ユーザーを表示')
    expect(permDesc('x.unknown:perm', 'Only en|中文')).toBe('Only en')
    await i18n.changeLanguage('en')
    expect(permDesc('x.unknown:perm', raw)).toBe('View users')
    await i18n.changeLanguage('zh-CN')
  })
  it('pickLangSegment 显式语言', () => {
    expect(pickLangSegment(raw, 'zh-CN')).toBe('查看用户')
    expect(pickLangSegment(raw, 'fr')).toBe('View users')
    expect(pickLangSegment('a||', 'ja')).toBe('a')
  })
})
