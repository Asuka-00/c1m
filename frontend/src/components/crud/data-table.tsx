import { useMemo } from 'react'
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
  type SortingState,
  type Updater,
} from '@tanstack/react-table'
import { t } from '@/i18n'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  DataTableColumnHeader,
  DataTablePagination,
} from '@/components/data-table'
import { DEFAULT_FILTERS, type FilterDef } from './filter-defs'
import { FilterToolbar } from './filters'
import type { ListParams } from './use-list-params'

/** DataTable 列定义。 */
export interface Column<T> {
  header: string
  cell: (row: T) => React.ReactNode
  /** 后端 sort_by 键；设置后列头可排序 */
  sortKey?: string
  className?: string
}

/**
 * 共享表格组件：服务端分页 + 排序（TanStack Table 手动模式），
 * 默认每页 20 条，可选每页条数，列头可排序，状态保存在 URL。
 * 传入 useListParams() 返回的 `params` 及 API 返回的 {data, count}。
 */
export function DataTable<T>({
  rows,
  total,
  columns,
  rowKey,
  params,
  loading,
  empty = t('common.noResults'),
  filters = DEFAULT_FILTERS,
  toolbar,
}: {
  rows: T[] | undefined
  total: number | undefined
  columns: Column<T>[]
  rowKey: (row: T) => string
  params: ListParams
  loading?: boolean
  empty?: string
  /** 声明式筛选（文本 / 下拉），显示在工具栏并保存在
   *  URL；默认为关键字搜索 `q`，传 [] 隐藏。需向
   *  useListParams() 传入相同定义。 */
  filters?: FilterDef[]
  /** 渲染在搜索框旁的额外工具栏内容（筛选） */
  toolbar?: React.ReactNode
}) {
  const defs = useMemo<ColumnDef<T>[]>(
    () =>
      columns.map((c, i) => ({
        id: c.sortKey ?? `col${i}`,
        // getCanSort() 需要 accessorFn；实际排序在服务端完成
        accessorFn: () => null,
        enableSorting: !!c.sortKey,
        enableHiding: false,
        header: ({ column }) => (
          <DataTableColumnHeader column={column} title={c.header} />
        ),
        cell: ({ row }) => c.cell(row.original),
        meta: { className: c.className },
      })),
    [columns]
  )
  const pagination: PaginationState = {
    pageIndex: params.page - 1,
    pageSize: params.pageSize,
  }
  const sorting: SortingState = params.sortBy
    ? [{ id: params.sortBy, desc: params.sortOrder === 'desc' }]
    : []
  // TanStack Table 返回的函数无法被 React Compiler 记忆化；这是
  // 已知且无害的不兼容（组件只是不会被自动记忆化）。
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: rows ?? [],
    columns: defs,
    getRowId: rowKey,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    rowCount: total ?? 0,
    state: { pagination, sorting },
    onPaginationChange: (u: Updater<PaginationState>) => {
      const next = typeof u === 'function' ? u(pagination) : u
      params.set(
        next.pageSize !== pagination.pageSize
          ? { pageSize: next.pageSize, page: 1 }
          : { page: next.pageIndex + 1 }
      )
    },
    onSortingChange: (u: Updater<SortingState>) => {
      const next = (typeof u === 'function' ? u(sorting) : u)[0]
      params.set({
        sortBy: next?.id,
        sortOrder: next?.desc ? 'desc' : 'asc',
        page: 1,
      })
    },
  })
  const cls = (m: unknown) =>
    (m as { className?: string } | undefined)?.className
  return (
    <div className='flex flex-col gap-3'>
      <FilterToolbar filters={filters} params={params}>
        {toolbar}
      </FilterToolbar>
      <div className='overflow-hidden rounded-md border'>
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id}>
                {hg.headers.map((h) => (
                  <TableHead
                    key={h.id}
                    className={cls(h.column.columnDef.meta)}
                  >
                    {flexRender(h.column.columnDef.header, h.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={defs.length} className='h-24 text-center'>
                  <Loader2 className='mx-auto animate-spin' />
                </TableCell>
              </TableRow>
            ) : table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((r) => (
                <TableRow key={r.id}>
                  {r.getVisibleCells().map((c) => (
                    <TableCell
                      key={c.id}
                      className={cls(c.column.columnDef.meta)}
                    >
                      {flexRender(c.column.columnDef.cell, c.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={defs.length}
                  className='h-24 text-center text-muted-foreground'
                >
                  {Object.keys(params.filters).length ? (
                    <div className='flex flex-col items-center gap-2'>
                      <span>
                        {params.q
                          ? t('table.noMatch', { q: params.q })
                          : t('table.noMatchFilters')}
                      </span>
                      <Button
                        variant='outline'
                        size='sm'
                        onClick={() =>
                          filters.forEach((f) => params.setFilter(f.name, ''))
                        }
                      >
                        {t('table.resetFilters')}
                      </Button>
                    </div>
                  ) : (
                    empty
                  )}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <div className='flex items-center justify-between gap-2'>
        <span className='text-sm whitespace-nowrap text-muted-foreground'>
          {t('common.total', { count: total ?? 0, formatParams: {} })}
        </span>
        <DataTablePagination table={table} className='flex-1' />
      </div>
    </div>
  )
}
