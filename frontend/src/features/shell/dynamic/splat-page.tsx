/** 兜底路由页面。 */
import { useParams } from '@tanstack/react-router'
import { DynamicPage } from './dynamic-page'

/** 兜底页面：根据 GET /menus/me 解析当前路径对应的组件。 */
export function SplatPage() {
  const { _splat } = useParams({ from: '/_authenticated/$' })
  return <DynamicPage path={`/${(_splat ?? '').replace(/\/$/, '')}`} />
}
