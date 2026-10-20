/** 流程图左侧面板：把工序 / 子流程拖到画布上添加工步。 */
import { useState, type DragEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { GitBranch, GripVertical, Search, Workflow } from 'lucide-react'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi, type MesRow } from '@/lib/api/mes/common'
import { Input } from '@/components/ui/input'

/** 拖放载荷：新工步使用的工序或子流程。 */
export type PaletteItem =
  | { kind: 'operation'; id: string }
  | { kind: 'sub_route'; id: string }

export const PALETTE_MIME = 'application/x-route-step'

function Item({
  item,
  title,
  sub,
  icon,
}: {
  item: PaletteItem
  title: string
  sub?: string
  icon: React.ReactNode
}) {
  const start = (e: DragEvent) => {
    e.dataTransfer.setData(PALETTE_MIME, JSON.stringify(item))
    e.dataTransfer.effectAllowed = 'copy'
  }
  return (
    <li
      draggable
      onDragStart={start}
      className='flex cursor-grab items-center gap-1.5 rounded-md border bg-card px-2 py-1.5 text-xs shadow-sm select-none hover:border-primary active:cursor-grabbing'
      data-testid={`palette-${item.kind}-${item.id}`}
    >
      <GripVertical className='size-3.5 shrink-0 text-muted-foreground' />
      {icon}
      <span className='min-w-0'>
        <span className='block truncate font-medium'>{title}</span>
        {sub && (
          <span className='block truncate text-muted-foreground'>{sub}</span>
        )}
      </span>
    </li>
  )
}

const label = (r: MesRow) => `${r.code} · ${r.name}`

/**
 * 工序 / 子流程选择列表，条目可拖到画布上。
 *
 * 子流程只列出已激活的子路线。
 */
export function Palette() {
  const tk = useTenantKey()
  const [q, setQ] = useState('')
  const ops = useQuery({
    queryKey: ['mes', 'operation', 'palette', tk, q],
    queryFn: () =>
      mesApi.list('operation', {
        q: q || undefined,
        page_size: 50,
        sort_by: 'code',
      }),
  })
  const subs = useQuery({
    queryKey: ['mes', 'route', 'palette-sub', tk],
    queryFn: () =>
      mesApi.list('route', {
        route_type: 'sub',
        status: 'active',
        page_size: 100,
      }),
  })
  const subRows = (subs.data?.data ?? []).filter(
    (r) => !q || label(r).toLowerCase().includes(q.toLowerCase())
  )
  return (
    <aside
      className='flex w-56 shrink-0 flex-col gap-2 border-e bg-muted/30 p-2'
      data-testid='flow-palette'
    >
      <p className='text-xs text-muted-foreground'>
        {t('mes.flow.paletteHint')}
      </p>
      <div className='relative'>
        <Search className='absolute start-2 top-2 size-3.5 text-muted-foreground' />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t('mes.flow.paletteSearch')}
          className='h-7 ps-7 text-xs'
        />
      </div>
      <div className='min-h-0 flex-1 space-y-3 overflow-y-auto pe-1'>
        <section className='space-y-1'>
          <h4 className='text-[11px] font-semibold text-muted-foreground uppercase'>
            {t('mes.field.route_step.operation')}
          </h4>
          <ul className='space-y-1'>
            {(ops.data?.data ?? []).map((o) => (
              <Item
                key={o.id}
                item={{ kind: 'operation', id: o.id }}
                title={label(o)}
                icon={<Workflow className='size-3.5 shrink-0 text-primary' />}
              />
            ))}
          </ul>
        </section>
        {subRows.length > 0 && (
          <section className='space-y-1'>
            <h4 className='text-[11px] font-semibold text-muted-foreground uppercase'>
              {t('mes.subRoute')}
            </h4>
            <ul className='space-y-1'>
              {subRows.map((r) => (
                <Item
                  key={r.id}
                  item={{ kind: 'sub_route', id: r.id }}
                  title={label(r)}
                  sub={`v${r.version}`}
                  icon={
                    <GitBranch className='size-3.5 shrink-0 text-primary' />
                  }
                />
              ))}
            </ul>
          </section>
        )}
      </div>
    </aside>
  )
}
