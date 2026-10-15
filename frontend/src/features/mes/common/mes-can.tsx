/** 按 MES 权限码渲染子元素的组件。 */
import type { ReactNode } from 'react'
import { type MesPerm, useMesCan } from './mes-perm'

/**
 * 按权限渲染子元素：有权限时渲染 `children`，否则渲染 `fallback`（默认不渲染）。
 * 需要“禁用而非隐藏”时直接用 `useMesCan()` 计算 `disabled`。
 */
export function MesCan({
  perm,
  children,
  fallback = null,
}: {
  perm: MesPerm
  children: ReactNode
  fallback?: ReactNode
}) {
  const can = useMesCan()
  return <>{can(perm) ? children : fallback}</>
}
