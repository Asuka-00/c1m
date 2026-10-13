import i18n from '@/i18n'
import { describe, expect, it } from 'vitest'
import { permKey, permLabel, roleLabel } from './rbac-labels'

describe('内置权限 / 角色名称', () => {
  it('编码转换为 i18n 键', () => {
    expect(permKey('mes.lot:start')).toBe('permName.mes_lot__start')
  })
  it('内置英文名按语言翻译，自定义名保留', async () => {
    await i18n.changeLanguage('zh-CN')
    expect(permLabel('users:read', 'View users')).toBe('查看用户')
    expect(permLabel('users:read', null)).toBe('查看用户')
    expect(permLabel('users:read', '自定义')).toBe('自定义')
    expect(permLabel('x:y', null)).toBe('x:y')
    expect(roleLabel({ name: 'owner', title: 'Owner' })).toBe('所有者')
    expect(roleLabel({ name: 'qa', title: '质检' })).toBe('质检')
    await i18n.changeLanguage('ja')
    expect(roleLabel({ name: 'member', title: null })).toBe('メンバー')
  })
})
