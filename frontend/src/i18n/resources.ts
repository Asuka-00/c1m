/**
 * 语言包：`locales/<语言>/**` 下按领域拆分的 YAML 文件，启动时按语言深度合并。
 *
 * 目录结构（各语言镜像）：
 * - `common.yaml` 通用文案；`menu.yaml` 菜单；`error.yaml` 错误提示与后端错误码（`error.code_<错误码>`）
 * - `modules/…` 各业务领域（认证、平台、MES 各后端模块）
 * 新增文案只需在对应领域文件里加键，三种语言保持同样的键。
 */
export type Tree = { [k: string]: string | Tree }

/** 支持的语言目录。 */
export const LOCALE_DIRS = ['zh-CN', 'ja', 'en'] as const

const files = import.meta.glob<Tree>('./locales/**/*.yaml', {
  eager: true,
  import: 'default',
})

/** 深度合并（后者覆盖前者）。 */
export function deepMerge(a: Tree, b: Tree): Tree {
  const out: Tree = { ...a }
  for (const [k, v] of Object.entries(b)) {
    const cur = out[k]
    out[k] =
      typeof v === 'object' && typeof cur === 'object' ? deepMerge(cur, v) : v
  }
  return out
}

/** 各语言合并后的完整语言包。 */
export const resources: Record<(typeof LOCALE_DIRS)[number], Tree> = {
  'zh-CN': {},
  ja: {},
  en: {},
}

for (const path of Object.keys(files).sort()) {
  const lang = /^\.\/locales\/([^/]+)\//.exec(path)?.[1] as
    | (typeof LOCALE_DIRS)[number]
    | undefined
  if (lang && lang in resources)
    resources[lang] = deepMerge(resources[lang], files[path])
}
