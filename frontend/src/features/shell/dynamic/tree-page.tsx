/**
 * 层级树页（如 工厂 › 区域 › 工作中心、仓库 › 库位）：左侧层级树，右侧为所选节点下级的列表。
 * 页签顺序即层级；下级实体通过引用上级实体的字段关联（自动从实体元数据识别）。
 * URL：`?tab=<层级页签>&<父字段>=<父 id>`，选中末级节点时为 `?tab=<末级>&id=<id>`。
 */
import { useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { t } from '@/i18n'
import { ChevronDown, ChevronRight, FolderTree } from 'lucide-react'
import type { MenuNode, MenuTab } from '@/lib/api'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi, type MesRow } from '@/lib/api/mes/common'
import { cn } from '@/lib/utils'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Page, PageEmbedContext } from '@/components/crud'
import { IconTooltip } from '@/components/icon-button'
import { rowLabel } from '@/features/mes/common/labels'
import { useMesMeta } from '@/features/mes/common/use-mes-meta'
import { ForbiddenError } from '@/features/shell/errors/forbidden'
import { pickTab, tabTitle } from './merged'
import { ComponentView } from './render'

/** 树每层最多加载的节点数（接口单页上限）。 */
const MAX_NODES = 100

/** 页签对应的实体编码（`mes:<entity>`）。 */
const entityOf = (tb: MenuTab) =>
  tb.component?.startsWith('mes:') ? tb.component.slice(4) : ''

/**
 * 层级树页。
 *
 * @param node - 合并菜单节点（component = tree，tabs 为各层级）
 */
export function TreePage({ node }: { node: MenuNode }) {
  const search = useSearch({ strict: false }) as Record<string, unknown>
  const navigate = useNavigate()
  const tk = useTenantKey()
  const { data: meta } = useMesMeta()
  const tabs = node.tabs ?? []
  const cur = pickTab(tabs, search.tab)
  const codes = tabs.map(entityOf)
  // 每层引用上级实体的字段列名（如 area.site_id）
  const parentCol = codes.map((c, i) => {
    const e = meta?.entities.find((x) => x.code === c)
    return i === 0
      ? ''
      : (e?.fields.find((f) => f.ref === codes[i - 1])?.column ?? '')
  })
  const levels = useQueries({
    queries: codes.map((c) => ({
      queryKey: ['mes', c, tk, 'tree-nodes'],
      queryFn: () => mesApi.list(c, { page_size: MAX_NODES }),
    })),
  })
  if (!cur) return <ForbiddenError />
  const go = (s: Record<string, unknown>) =>
    navigate({ to: '.', search: s as never, replace: true })
  const rows = (i: number, parent?: string): MesRow[] =>
    (levels[i]?.data?.data ?? []).filter(
      (r) => i === 0 || String(r[parentCol[i]]) === parent
    )
  const curIdx = tabs.findIndex((x) => x.key === cur.key)
  // 当前选中节点：上级过滤值或末级 id
  const selected = String(
    (curIdx > 0 && search[parentCol[curIdx]]) ||
      (curIdx === tabs.length - 1 && search.id) ||
      ''
  )
  // 选中节点及其祖先（默认展开）
  const trail = new Set<string>()
  let lv = curIdx === tabs.length - 1 && search.id ? curIdx : curIdx - 1
  let at: MesRow | undefined = (levels[lv]?.data?.data ?? []).find(
    (r) => String(r.id) === selected
  )
  while (at && lv >= 0) {
    trail.add(String(at.id))
    const pid = lv > 0 ? String(at[parentCol[lv]]) : ''
    lv -= 1
    at =
      lv >= 0
        ? levels[lv]?.data?.data.find((r) => String(r.id) === pid)
        : undefined
  }
  /** 点击节点：显示其下级列表；末级节点显示自身。 */
  const open = (i: number, r: MesRow) =>
    i + 1 < tabs.length
      ? go({ tab: tabs[i + 1].key, [parentCol[i + 1]]: r.id })
      : go({ tab: tabs[i].key, id: r.id })
  return (
    <Page title={tabTitle(node.key, node.title)}>
      <div className='grid gap-4 lg:grid-cols-[16rem_1fr]'>
        <aside
          className='rounded-md border p-2 text-sm lg:max-h-[75vh] lg:overflow-y-auto'
          data-testid='hier-tree'
        >
          <button
            type='button'
            className={cn(
              'flex w-full items-center gap-2 rounded px-2 py-1 text-start hover:bg-muted',
              !selected && curIdx === 0 && 'bg-muted font-medium'
            )}
            onClick={() => go({ tab: tabs[0].key })}
          >
            <FolderTree className='size-4 text-muted-foreground' />
            {t('mes.tree.all', { name: tabTitle(tabs[0].key, tabs[0].title) })}
          </button>
          <Level
            i={0}
            rows={rows}
            depth={tabs.length}
            selected={selected}
            trail={trail}
            onOpen={open}
          />
        </aside>
        <div className='flex min-w-0 flex-col gap-3'>
          <Tabs value={cur.key} onValueChange={(v) => go({ tab: v })}>
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
        </div>
      </div>
    </Page>
  )
}

/** 树的一层（递归渲染下级）。 */
function Level({
  i,
  parent,
  rows,
  depth,
  selected,
  trail,
  onOpen,
}: {
  i: number
  parent?: string
  rows: (i: number, parent?: string) => MesRow[]
  depth: number
  selected: string
  trail: Set<string>
  onOpen: (i: number, r: MesRow) => void
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const items = rows(i, parent)
  if (!items.length) return null
  return (
    <ul className={cn(i > 0 && 'ms-4 border-s ps-1')}>
      {items.map((r) => {
        const id = String(r.id)
        const leaf = i + 1 >= depth
        const expanded = open[id] ?? trail.has(id)
        return (
          <li key={id}>
            <div
              className={cn(
                'flex items-center gap-1 rounded px-1 py-0.5 hover:bg-muted',
                selected === id && 'bg-muted font-medium'
              )}
            >
              {leaf ? (
                <span className='size-5' />
              ) : (
                <IconTooltip
                  label={
                    expanded ? t('mes.tree.collapse') : t('mes.tree.expand')
                  }
                >
                  <button
                    type='button'
                    className='rounded p-0.5'
                    aria-label={
                      expanded ? t('mes.tree.collapse') : t('mes.tree.expand')
                    }
                    onClick={() => setOpen((o) => ({ ...o, [id]: !expanded }))}
                  >
                    {expanded ? (
                      <ChevronDown className='size-4' />
                    ) : (
                      <ChevronRight className='size-4' />
                    )}
                  </button>
                </IconTooltip>
              )}
              <button
                type='button'
                className='min-w-0 flex-1 truncate text-start'
                title={rowLabel(r)}
                onClick={() => onOpen(i, r)}
              >
                {rowLabel(r)}
              </button>
            </div>
            {!leaf && expanded && (
              <Level
                i={i + 1}
                parent={id}
                rows={rows}
                depth={depth}
                selected={selected}
                trail={trail}
                onOpen={onOpen}
              />
            )}
          </li>
        )
      })}
    </ul>
  )
}
