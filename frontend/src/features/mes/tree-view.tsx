import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { ChevronRight, Loader2, Pencil } from 'lucide-react'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi, type MesEntity, type MesTreeNode } from '@/lib/api/mes'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cellValue } from './cells'

/** Hierarchy of a `tree` entity (parent_id); nodes expanded to depth 1. */
export function TreeView({
  entity: e,
  onEdit,
}: {
  entity: MesEntity
  onEdit: (n: MesTreeNode) => void
}) {
  const tk = useTenantKey()
  const { data, isLoading } = useQuery({
    queryKey: ['mes', e.code, 'tree', tk],
    queryFn: () => mesApi.tree(e.code),
  })
  if (isLoading) return <Loader2 className='mx-auto animate-spin' />
  if (!data?.length)
    return (
      <p className='text-sm text-muted-foreground'>{t('common.noResults')}</p>
    )
  // show the first enum/ref columns as context next to each node
  const extra = e.fields
    .filter(
      (f) => f.list && ['enum', 'ref'].includes(f.type) && f.name !== 'parent'
    )
    .slice(0, 2)
  return (
    <div className='rounded-md border p-2' data-testid='mes-tree'>
      {data.map((n) => (
        <Node
          key={n.id}
          n={n}
          depth={0}
          e={e}
          extra={extra.map((f) => f.name)}
          onEdit={onEdit}
        />
      ))}
    </div>
  )
}

function Node({
  n,
  depth,
  e,
  extra,
  onEdit,
}: {
  n: MesTreeNode
  depth: number
  e: MesEntity
  extra: string[]
  onEdit: (n: MesTreeNode) => void
}) {
  const [open, setOpen] = useState(depth < 1)
  const has = n.children.length > 0
  return (
    <div>
      <div
        className='group flex items-center gap-1 rounded px-1 py-1 hover:bg-muted/60'
        style={{ paddingInlineStart: depth * 20 + 4 }}
      >
        <button
          type='button'
          className={cn('size-5 shrink-0', !has && 'invisible')}
          onClick={() => setOpen(!open)}
          aria-label={open ? t('common.collapse') : t('common.expand')}
        >
          <ChevronRight
            className={cn('size-4 transition-transform', open && 'rotate-90')}
          />
        </button>
        <span className='font-medium'>{String(n.code ?? n.id)}</span>
        {n.name && (
          <span className='text-muted-foreground'>· {String(n.name)}</span>
        )}
        {extra.map((x) => (
          <span key={x} className='text-xs'>
            {cellValue(e, n, x)}
          </span>
        ))}
        {has && (
          <Badge variant='secondary' className='ms-1'>
            {n.children.length}
          </Badge>
        )}
        {e.can_write && (
          <Button
            size='icon'
            variant='ghost'
            className='ms-auto size-7 opacity-0 group-hover:opacity-100'
            aria-label={t('common.edit')}
            onClick={() => onEdit(n)}
          >
            <Pencil className='size-3.5' />
          </Button>
        )}
      </div>
      {open &&
        n.children.map((c) => (
          <Node
            key={c.id}
            n={c}
            depth={depth + 1}
            e={e}
            extra={extra}
            onEdit={onEdit}
          />
        ))}
    </div>
  )
}
