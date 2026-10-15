/**
 * 坐标图列表（P2-F8 / P2-B5）：分页列出已导入的坐标图，同一基板多版本都列出并标出最新版本；
 * 按基板编号、基板编号 / 文件名搜索、导入日期筛选，可只看最新版本。需要 mes.map:read。
 */
import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { useTenantKey } from '@/lib/api/hooks'
import { mapApi, mapApiError } from '@/lib/api/mes/map'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { rangeInverted } from '@/components/crud/filter-defs'
import { MES_PERM, useMesCan } from '@/features/mes/common/mes-perm'
import { mapErrorMessage } from './map-errors'
import {
  MAP_PAGE_SIZE,
  emptyMapFilter,
  mapListParams,
  type MapListFilter,
} from './map-list-params'

export function MapList() {
  const tk = useTenantKey()
  const canRead = useMesCan()(MES_PERM.mapRead)
  const [f, setF] = useState<MapListFilter>(emptyMapFilter)
  const set = (p: Partial<MapListFilter>) =>
    setF((x) => ({ ...x, page: 1, ...p }))
  const params = mapListParams(f)
  const q = useQuery({
    queryKey: ['mes', 'map', tk, 'list', params],
    queryFn: () => mapApi.list(params),
    enabled: canRead,
    placeholderData: keepPreviousData,
    retry: false,
  })
  const count = q.data?.count ?? 0
  const pages = Math.max(1, Math.ceil(count / MAP_PAGE_SIZE))
  return (
    <section className='flex flex-col gap-2' data-testid='map-list'>
      <h3 className='font-medium'>{t('mes.mapList.title')}</h3>
      {!canRead ? (
        <p className='text-sm text-muted-foreground'>
          {t('mes.map.noPermission')}
        </p>
      ) : (
        <>
          <div className='flex flex-wrap items-end gap-2'>
            <Input
              className='w-44'
              aria-label={t('mes.mapList.q')}
              placeholder={t('mes.mapList.q')}
              value={f.q}
              onChange={(e) => set({ q: e.target.value })}
            />
            <Input
              className='w-40'
              aria-label={t('mes.map.substrate')}
              placeholder={t('mes.map.substrate')}
              value={f.substrate}
              onChange={(e) => set({ substrate: e.target.value })}
            />
            <div className='grid gap-1'>
              <Label htmlFor='map-from' className='text-xs'>
                {t('mes.mapList.from')}
              </Label>
              <Input
                id='map-from'
                type='date'
                className='w-40'
                value={f.from}
                max={f.to || undefined}
                onChange={(e) => set({ from: e.target.value })}
              />
            </div>
            <div className='grid gap-1'>
              <Label htmlFor='map-to' className='text-xs'>
                {t('mes.mapList.to')}
              </Label>
              <Input
                id='map-to'
                type='date'
                className='w-40'
                value={f.to}
                min={f.from || undefined}
                onChange={(e) => set({ to: e.target.value })}
              />
            </div>
            {rangeInverted(f.from, f.to) && (
              <p
                className='text-sm text-destructive'
                data-testid='range-inverted'
              >
                {t('errors.rangeInverted')}
              </p>
            )}
            <Label className='flex h-9 items-center gap-2 font-normal'>
              <Checkbox
                checked={f.latestOnly}
                onCheckedChange={(v) => set({ latestOnly: !!v })}
              />
              {t('mes.mapList.latestOnly')}
            </Label>
          </div>
          {q.error && (
            <p className='text-sm text-destructive'>
              {mapErrorMessage(mapApiError(q.error))}
            </p>
          )}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('mes.map.substrate')}</TableHead>
                <TableHead>{t('mes.mapList.version')}</TableHead>
                <TableHead className='text-end'>
                  {t('mes.mapList.total')}
                </TableHead>
                <TableHead className='text-end'>
                  {t('mes.mapList.good')}
                </TableHead>
                <TableHead className='text-end'>
                  {t('mes.mapList.excluded')}
                </TableHead>
                <TableHead>{t('mes.mapList.binSet')}</TableHead>
                <TableHead>{t('mes.mapList.lot')}</TableHead>
                <TableHead>{t('mes.mapList.file')}</TableHead>
                <TableHead>{t('mes.mapList.importedBy')}</TableHead>
                <TableHead>{t('mes.mapList.importedAt')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(q.data?.data ?? []).map((m) => (
                <TableRow key={m.id} data-testid='map-row'>
                  <TableCell className='font-mono'>{m.substrate_id}</TableCell>
                  <TableCell>
                    v{m.map_version}
                    {m.is_latest && (
                      <Badge variant='secondary' className='ms-2'>
                        {t('mes.mapList.latest')}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className='text-end'>{m.total_qty}</TableCell>
                  <TableCell className='text-end'>
                    {m.good_qty ?? '—'}
                  </TableCell>
                  <TableCell className='text-end'>
                    {m.excluded_qty ?? '—'}
                  </TableCell>
                  <TableCell>
                    {m.bin_set_code
                      ? `${m.bin_set_code} v${m.bin_set_version ?? ''}`
                      : '—'}
                  </TableCell>
                  <TableCell>{m.lot_code ?? '—'}</TableCell>
                  <TableCell>
                    {m.file_name ?? '—'}
                    {m.source && (
                      <span className='ms-1 text-xs text-muted-foreground'>
                        ({m.source})
                      </span>
                    )}
                  </TableCell>
                  <TableCell>{m.imported_by ?? '—'}</TableCell>
                  <TableCell>
                    {m.imported_at ? fmtDateTime(m.imported_at) : '—'}
                  </TableCell>
                </TableRow>
              ))}
              {q.data && q.data.data.length === 0 && (
                <TableRow>
                  <TableCell colSpan={10} className='text-muted-foreground'>
                    {t('common.noResults')}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
          <div className='flex items-center justify-end gap-2 text-sm'>
            <span className='text-muted-foreground' data-testid='map-count'>
              {t('mes.mapList.count', { count, page: f.page, pages })}
            </span>
            <Button
              size='sm'
              variant='outline'
              disabled={f.page <= 1}
              onClick={() => setF((x) => ({ ...x, page: x.page - 1 }))}
            >
              {t('mes.mapList.prev')}
            </Button>
            <Button
              size='sm'
              variant='outline'
              disabled={f.page >= pages}
              onClick={() => setF((x) => ({ ...x, page: x.page + 1 }))}
            >
              {t('mes.mapList.next')}
            </Button>
          </div>
        </>
      )}
    </section>
  )
}
