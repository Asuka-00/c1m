import type { ComponentType, LazyExoticComponent } from 'react'

/** menu component key -> lazily loaded page */
export type Pages = Record<string, LazyExoticComponent<ComponentType>>
