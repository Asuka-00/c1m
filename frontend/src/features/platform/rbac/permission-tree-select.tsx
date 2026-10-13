/** 嵌入角色对话框的可折叠三态复选权限树。 */
import { useState } from 'react'
import { t } from '@/i18n'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { PermNode } from '@/lib/api'
import { permDesc } from '@/lib/rbac-labels'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
  allIds,
  checkState,
  filterTree,
  nodeCodes,
  nodeLabel,
  toggleNode,
} from './tree'
import { TypeBadge } from './type-badge'

/** 权限复选树：菜单 → 页面 → 按钮；父节点三态，勾选父节点作用于全部后代。 */
export function PermissionTreeSelect({
  nodes,
  value,
  onChange,
  disabled,
}: {
  nodes: PermNode[]
  value: string[]
  onChange: (codes: string[]) => void
  disabled?: boolean
}) {
  const selected = new Set(value)
  const [open, setOpen] = useState<Set<string>>(
    () => new Set(nodes.map((n) => n.id))
  )
  const [q, setQ] = useState('')
  const shown = filterTree(
    nodes.filter((n) => nodeCodes(n).length),
    q
  )
  const total = new Set(nodes.flatMap(nodeCodes)).size
  const render = (n: PermNode, depth: number): React.ReactNode => {
    const codes = nodeCodes(n)
    if (!codes.length) return null
    const isOpen = !!q || open.has(n.id)
    const hasKids = n.children.some((c) => nodeCodes(c).length)
    return (
      <div
        key={n.id}
        role='treeitem'
        aria-expanded={hasKids ? isOpen : undefined}
      >
        <div
          className='flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-muted/50'
          style={{ paddingInlineStart: depth * 20 + 8 }}
        >
          {hasKids ? (
            <button
              type='button'
              className='text-muted-foreground'
              aria-label={isOpen ? t('common.collapse') : t('common.expand')}
              onClick={() => {
                const s = new Set(open)
                if (isOpen) s.delete(n.id)
                else s.add(n.id)
                setOpen(s)
              }}
            >
              {isOpen ? (
                <ChevronDown className='size-4' />
              ) : (
                <ChevronRight className='size-4' />
              )}
            </button>
          ) : (
            <span className='w-4' />
          )}
          <Checkbox
            checked={checkState(n, selected)}
            disabled={disabled}
            aria-label={nodeLabel(n)}
            onCheckedChange={(c) =>
              onChange([...toggleNode(n, selected, c === true)])
            }
          />
          <span
            className={n.kind === 'perm' ? '' : 'font-medium'}
            title={
              n.kind === 'perm' ? permDesc(n.code, n.description) : undefined
            }
          >
            {nodeLabel(n)}
          </span>
          {n.code && (
            <code className='text-xs text-muted-foreground'>{n.code}</code>
          )}
          <TypeBadge type={n.type} className='ms-auto' />
        </div>
        {hasKids && isOpen && (
          <div role='group'>{n.children.map((c) => render(c, depth + 1))}</div>
        )}
      </div>
    )
  }
  return (
    <div className='grid gap-2'>
      <div className='flex items-center gap-2'>
        <Input
          className='h-8'
          placeholder={t('rbac.searchTree')}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <Button
          type='button'
          size='sm'
          variant='ghost'
          onClick={() => setOpen(new Set(allIds(nodes)))}
        >
          {t('rbac.expandAll')}
        </Button>
        <Button
          type='button'
          size='sm'
          variant='ghost'
          onClick={() => setOpen(new Set())}
        >
          {t('rbac.collapseAll')}
        </Button>
        <span className='text-xs whitespace-nowrap text-muted-foreground'>
          {t('rbac.selectedOf', { n: value.length, total })}
        </span>
      </div>
      <div
        role='tree'
        className='max-h-80 overflow-auto rounded-md border py-1'
      >
        {shown.map((n) => render(n, 0))}
        {!shown.length && (
          <p className='p-3 text-sm text-muted-foreground'>
            {t('common.noResults')}
          </p>
        )}
      </div>
    </div>
  )
}
