/** 树形实体（如设备：主设备 → 腔体 / 装载口）的树形视图。 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react'
import { useTenantKey } from '@/lib/api/hooks'
import {
  mesApi,
  type MesEntity,
  type MesRow,
  type MesTreeNode,
} from '@/lib/api/mes/common'
import { cn } from '@/lib/utils'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { Column } from '@/components/crud'
import { IconButton } from '@/components/icon-button'

/** 关键字过滤：保留匹配节点及其祖先。 */
function prune(nodes: MesTreeNode[], q: string): MesTreeNode[] {
  if (!q) return nodes
  const hit = (n: MesTreeNode) =>
    `${n.code ?? ''} ${n.name ?? ''}`.toLowerCase().includes(q)
  return nodes.flatMap((n) => {
    const kids = prune(n.children, q)
    return hit(n) || kids.length ? [{ ...n, children: kids }] : []
  })
}

/**
 * 树形视图：可展开 / 收起，关键字过滤（保留祖先），列与表格视图一致。
 *
 * @param entity - 实体元数据（tree = true）
 * @param columns - 表格列（首列前显示展开按钮与缩进）
 */
export function EntityTree({
  entity: e,
  columns,
}: {
  entity: MesEntity
  columns: Column<MesRow>[]
}) {
  const tk = useTenantKey()
  const q = useQuery({
    queryKey: ['mes', e.code, tk, 'tree'],
    queryFn: () => mesApi.tree(e.code),
  })
  const [kw, setKw] = useState('')
  const [closed, setClosed] = useState<Set<string>>(new Set())
  const nodes = useMemo(
    () => prune(q.data ?? [], kw.trim().toLowerCase()),
    [q.data, kw]
  )
  const toggle = (id: string) =>
    setClosed((s) => {
      const n = new Set(s)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  const rows: { n: MesTreeNode; depth: number }[] = []
  const walk = (ns: MesTreeNode[], depth: number) =>
    ns.forEach((n) => {
      rows.push({ n, depth })
      if (!closed.has(n.id) || kw) walk(n.children, depth + 1)
    })
  walk(nodes, 0)
  return (
    <div className='space-y-3'>
      <Input
        className='max-w-sm'
        value={kw}
        onChange={(ev) => setKw(ev.target.value)}
        placeholder={t('table.search')}
        data-testid='tree-search'
      />
      <div className='rounded-md border'>
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((c, i) => (
                <TableHead key={i} className={c.className}>
                  {c.header}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {q.isLoading && (
              <TableRow>
                <TableCell colSpan={columns.length}>
                  <Loader2 className='mx-auto animate-spin' />
                </TableCell>
              </TableRow>
            )}
            {!q.isLoading && rows.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className='h-20 text-center text-muted-foreground'
                >
                  {t('common.noResults')}
                </TableCell>
              </TableRow>
            )}
            {rows.map(({ n, depth }) => (
              <TableRow key={n.id}>
                {columns.map((c, i) => (
                  <TableCell
                    key={i}
                    className={cn(
                      c.className,
                      i === columns.length - 1 &&
                        !c.header &&
                        'sticky end-0 z-10 bg-background'
                    )}
                  >
                    {i === 0 ? (
                      <span
                        className='inline-flex items-center gap-1'
                        style={{ paddingInlineStart: depth * 20 }}
                      >
                        {n.children.length ? (
                          <IconButton
                            label={t('mes.treeToggle')}
                            variant='ghost'
                            className='size-6'
                            onClick={() => toggle(n.id)}
                          >
                            {closed.has(n.id) && !kw ? (
                              <ChevronRight className='size-4' />
                            ) : (
                              <ChevronDown className='size-4' />
                            )}
                          </IconButton>
                        ) : (
                          <span className='inline-block w-6' />
                        )}
                        {c.cell(n)}
                      </span>
                    ) : (
                      c.cell(n)
                    )}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
