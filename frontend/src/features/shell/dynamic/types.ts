/** 动态页面注册表类型。 */
import type { ComponentType, LazyExoticComponent } from 'react'

/** 菜单组件 key -> 懒加载页面 */
export type Pages = Record<string, LazyExoticComponent<ComponentType>>
