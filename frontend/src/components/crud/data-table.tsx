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

export interface Column<T> {
  header: string
  cell: (row: T) => React.ReactNode
  /** backend sort_by key; makes the column header sortable */
  sortKey?: string
  className?: string
}

/**
 * THE shared table: server-side pagination + sorting (TanStack Table manual mode),
 * default 20 rows/page, page-size selector, sortable headers, state in the URL.
 * Feed it `params` from useListParams() and the {data, count} page from the API.
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
  /** declarative filters (text / select) shown in the toolbar and kept in the
   *  URL; default: keyword search `q`. Pass [] to hide. Give the same defs to
   *  useListParams(). */
  filters?: FilterDef[]
  /** extra toolbar content (filters) rendered next to the search box */
  toolbar?: React.ReactNode
}) {
  const defs = useMemo<ColumnDef<T>[]>(
    () =>
      columns.map((c, i) => ({
        id: c.sortKey ?? `col${i}`,
        // accessorFn is required for getCanSort(); sorting itself happens server-side
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
  // TanStack Table returns functions the React Compiler cannot memoize; this is a
  // known, harmless incompatibility (the component simply isn't auto-memoized).
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
