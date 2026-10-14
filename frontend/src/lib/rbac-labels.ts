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

/**
 * 内置权限说明（数据库中仍为内置英文说明时按语言翻译，自定义说明保留）。
 *
 * @param code - 权限编码
 * @param desc - 数据库中的说明
 * @returns 当前语言下的说明
 */
export const permDesc = (code: string, desc?: string | null) => {
  const key = permKey(code).replace(/^permName\./, 'permDesc.')
  // 后端内置说明为 'en|zh|ja' 三语串：有前端文案时一律用文案，否则按语言取段，绝不显示原始串
  if (desc && desc.includes('|'))
    return i18n.exists(key) ? t(key) : pickLangSegment(desc)
  return localize(key, desc, desc ?? '')
}

/**
 * 从 'en|zh|ja' 三语串中取当前语言对应的一段（en=0、zh=1、ja=2），缺失或为空时回退 en。
 *
 * @param s - 三语串
 * @param lng - 语言（默认 i18n 当前语言）
 * @returns 对应语言的文本
 */
export function pickLangSegment(
  s: string,
  lng: string = i18n.language ?? 'en'
) {
  const parts = s.split('|').map((x) => x.trim())
  const l = lng.toLowerCase()
  const idx = l.startsWith('zh') ? 1 : l.startsWith('ja') ? 2 : 0
  return parts[idx] || parts[0] || ''
}

/**
 * 内置角色说明（平台角色与工作区默认角色分开翻译，自定义说明保留）。
 *
 * @param r - 角色（name 为编码，description 为说明）
 * @param platform - 是否为平台角色
 * @returns 当前语言下的说明
 */
export const roleDesc = (
  r: { name: string; description?: string | null },
  platform: boolean
) =>
  localize(
    `roleDesc.${platform ? 'platform_' : ''}${r.name}`,
    r.description,
    r.description ?? ''
  )
