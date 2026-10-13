/** 内置权限 / 角色名称的本地化（后端生成的 permName.* / roleName.* i18n 包）。 */
import i18n, { t } from '@/i18n'

/**
 * 权限编码 -> i18n 键（与后端 labels.i18n_key 一致，避开 i18next 的 . 与 : 分隔符）。
 *
 * @param code - 权限编码，如 `mes.lot:start`
 * @returns 如 `permName.mes_lot__start`
 */
export const permKey = (code: string) =>
  `permName.${code.replace(/\./g, '_').replace(/:/g, '__')}`

/** 名称为空或仍是内置英文名时使用翻译，否则保留自定义名称。 */
function localize(key: string, name: string | null | undefined, fb: string) {
  if (!i18n.exists(key)) return name || fb
  const en = i18n.getFixedT('en')(key)
  return !name || name === en ? t(key) : name
}

/**
 * 权限显示名称。
 *
 * @param code - 权限编码
 * @param name - 数据库中的名称（可能为内置英文名或自定义名）
 * @returns 当前语言下的名称
 */
export const permLabel = (code: string, name?: string | null) =>
  localize(permKey(code), name, code)

/**
 * 角色显示名称（内置角色 admin / user / owner / member 按语言翻译）。
 *
 * @param r - 角色（name 为编码，title 为显示名称）
 * @returns 当前语言下的名称
 */
export const roleLabel = (r: { name: string; title?: string | null }) =>
  localize(`roleName.${r.name}`, r.title, r.name)
