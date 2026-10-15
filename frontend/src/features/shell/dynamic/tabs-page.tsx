/** 合并菜单页签页：标题 + 页签（URL ?tab=），各页签复用原页面组件（嵌入模式）。 */
import { useNavigate, useSearch } from '@tanstack/react-router'
import type { MenuNode } from '@/lib/api'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Page, PageEmbedContext } from '@/components/crud'
import { ForbiddenError } from '@/features/shell/errors/forbidden'
import { pickTab, tabTitle } from './merged'
import { ComponentView } from './render'

/**
 * 页签页。切换页签时只保留 `tab` 参数（各页签的分页 / 筛选互不串扰）。
 *
 * @param node - 合并菜单节点（tabs 已按权限过滤）
 */
export function TabsPage({ node }: { node: MenuNode }) {
  const search = useSearch({ strict: false }) as Record<string, unknown>
  const navigate = useNavigate()
  const tabs = node.tabs ?? []
  const cur = pickTab(tabs, search.tab)
  if (!cur) return <ForbiddenError inApp />
  return (
    <Page title={tabTitle(node.key, node.title)}>
      <Tabs
        value={cur.key}
        onValueChange={(v) =>
          navigate({ to: '.', search: { tab: v } as never, replace: true })
        }
      >
        <TabsList data-testid='merged-tabs'>
          {tabs.map((x) => (
            <TabsTrigger key={x.key} value={x.key} data-tab={x.key}>
              {tabTitle(x.key, x.title)}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      <PageEmbedContext.Provider value>
        <ComponentView key={cur.key} component={cur.component} />
      </PageEmbedContext.Provider>
    </Page>
  )
}
