/** 层级树页（P2 实现）。 */
import type { MenuNode } from '@/lib/api'
import { TabsPage } from './tabs-page'

/** 层级树页：暂按页签显示。 */
export function TreePage({ node }: { node: MenuNode }) {
  return <TabsPage node={node} />
}
