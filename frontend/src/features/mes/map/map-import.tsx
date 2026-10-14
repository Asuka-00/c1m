/**
 * 坐标图 / bin 定义集导入（P1 / F1，真实接口）：选择类型 → 上传 CSV → 预览逐行报错 → 确认导入；
 * 下方可按基板编号查询已导入的坐标图（各版本）。时间按本地时区显示。
 */
import { useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { Search, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import {
  fileBody,
  mapApi,
  mapApiError,
  type BinSetPreview,
  type MapApiError,
  type MapPreview,
  type MapRowError,
  type SubstrateMap,
} from '@/lib/api/mes/map'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Page } from '@/components/crud'
import { MES_PERM, useMesCan } from '@/features/mes/common/mes-perm'
import { mapErrorMessage } from './map-errors'
import { MapList } from './map-list'

type Kind = 'map' | 'binSet'
type Preview =
  | { kind: 'map'; data: MapPreview }
  | { kind: 'binSet'; data: BinSetPreview }

const rowErrorText = (e: MapRowError) =>
  t(`mes.map.errors.${e.code}`, { defaultValue: e.message })

/** 坐标图导入页面。 */
export default function MapImport() {
  const can = useMesCan()
  const canImport = can(MES_PERM.mapImport)
  const input = useRef<HTMLInputElement>(null)
  const [kind, setKind] = useState<Kind>('map')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [failure, setFailure] = useState<MapApiError | null>(null)
  const [imported, setImported] = useState<SubstrateMap[]>([])

  const reset = () => {
    setFile(null)
    setPreview(null)
    setFailure(null)
    if (input.current) input.current.value = ''
  }

  const check = useMutation({
    mutationFn: async ({ f, k }: { f: File; k: Kind }): Promise<Preview> => {
      const body = await fileBody(f)
      return k === 'map'
        ? { kind: 'map', data: await mapApi.preview(body) }
        : { kind: 'binSet', data: await mapApi.binSetPreview(body) }
    },
    onSuccess: setPreview,
    onError: (e) => {
      const err = mapApiError(e)
      setFailure(err)
      toast.error(mapErrorMessage(err))
    },
  })
  const commit = useMutation({
    mutationFn: async ({ f, k }: { f: File; k: Kind }) => {
      const body = await fileBody(f)
      return k === 'map'
        ? ({ kind: 'map', res: await mapApi.commit(body) } as const)
        : ({ kind: 'binSet', res: await mapApi.binSetCommit(body) } as const)
    },
    onSuccess: (r) => {
      if (r.kind === 'map') {
        toast.success(t('mes.map.imported', { n: r.res.data.length }))
        setImported((prev) => [...r.res.data, ...prev])
      } else {
        toast.success(
          t('mes.map.binSetImported', {
            code: r.res.code,
            version: r.res.version,
          })
        )
      }
      reset()
    },
    onError: (e) => {
      const err = mapApiError(e)
      setFailure(err)
      toast.error(mapErrorMessage(err))
    },
  })

  const pick = (f: File | null) => {
    setFile(f)
    setPreview(null)
    setFailure(null)
    if (f) check.mutate({ f, k: kind })
  }
  const switchKind = (k: Kind) => {
    setKind(k)
    reset()
  }
  const ok = !!preview?.data.ok
  const rowErrors =
    failure?.kind === 'rows' ? failure.errors : (preview?.data.errors ?? [])

  return (
    <Page title={t('mes.map.title')} description={t('mes.map.description')}>
      <div className='flex flex-wrap items-center gap-2'>
        <div className='flex gap-1' role='group'>
          {(['map', 'binSet'] as const).map((k) => (
            <Button
              key={k}
              size='sm'
              variant={kind === k ? 'default' : 'outline'}
              aria-pressed={kind === k}
              onClick={() => switchKind(k)}
            >
              {t(`mes.map.kind.${k}`)}
            </Button>
          ))}
        </div>
        <input
          ref={input}
          type='file'
          accept='.csv,text/csv'
          className='hidden'
          aria-label={t('mes.map.chooseFile')}
          onChange={(e) => pick(e.target.files?.[0] ?? null)}
        />
        <Button
          variant='outline'
          onClick={() => input.current?.click()}
          disabled={!canImport}
          title={canImport ? undefined : t('mes.map.noPermission')}
        >
          <Upload />
          {t('mes.map.chooseFile')}
        </Button>
        {file && (
          <span className='text-sm text-muted-foreground'>{file.name}</span>
        )}
        <Button
          className='ms-auto'
          disabled={!ok || !file || commit.isPending || !canImport}
          title={canImport ? undefined : t('mes.map.noPermission')}
          onClick={() => file && commit.mutate({ f: file, k: kind })}
        >
          {t('mes.map.confirm')}
        </Button>
      </div>

      {failure && failure.kind !== 'rows' && (
        <Alert variant='destructive'>
          <AlertTitle>{t('mes.map.fileError')}</AlertTitle>
          <AlertDescription>{mapErrorMessage(failure)}</AlertDescription>
        </Alert>
      )}

      {rowErrors.length > 0 && <ErrorTable errors={rowErrors} />}

      {preview?.kind === 'map' && preview.data.ok && (
        <SummaryTable rows={preview.data.substrates} />
      )}
      {preview?.kind === 'binSet' && preview.data.ok && (
        <BinSetTable data={preview.data} />
      )}

      {imported.length > 0 && (
        <section className='flex flex-col gap-2'>
          <h3 className='font-medium'>{t('mes.map.listTitle')}</h3>
          <MapTable rows={imported} />
        </section>
      )}

      <Lookup />
      <MapList />
    </Page>
  )
}

function ErrorTable({ errors }: { errors: MapRowError[] }) {
  return (
    <section className='flex flex-col gap-2'>
      <h3 className='font-medium'>
        {t('mes.map.hasErrors', { n: errors.length })}
      </h3>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t('mes.map.rowNo')}</TableHead>
            <TableHead>{t('mes.map.field')}</TableHead>
            <TableHead>{t('mes.map.problem')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {errors.map((e, i) => (
            <TableRow key={`${e.row_no}-${e.code}-${i}`}>
              <TableCell
                title={
                  e.file_line == null
                    ? undefined
                    : t('mes.map.fileLine', { n: e.file_line })
                }
              >
                {e.row_no ?? t('mes.map.wholeFile')}
              </TableCell>
              <TableCell>{e.field ?? '—'}</TableCell>
              <TableCell title={e.message}>{rowErrorText(e)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  )
}

/** 坐标图预览通过时按基板汇总。 */
function SummaryTable({ rows }: { rows: MapPreview['substrates'] }) {
  return (
    <section className='flex flex-col gap-2'>
      <h3 className='font-medium'>
        {t('mes.map.previewOk', { n: rows.length })}
      </h3>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t('mes.map.substrate')}</TableHead>
            <TableHead>{t('mes.map.version')}</TableHead>
            <TableHead>{t('mes.map.size')}</TableHead>
            <TableHead>{t('mes.map.total')}</TableHead>
            <TableHead>{t('mes.map.good')}</TableHead>
            <TableHead>{t('mes.map.excluded')}</TableHead>
            <TableHead>{t('mes.map.binCounts')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((s) => (
            <TableRow key={s.code}>
              <TableCell>{s.code}</TableCell>
              <TableCell>
                <Badge variant='outline'>v{s.map_version}</Badge>
              </TableCell>
              <TableCell>
                {s.rows}×{s.cols}
              </TableCell>
              <TableCell>{s.total_qty}</TableCell>
              <TableCell>{s.good_qty}</TableCell>
              <TableCell>{s.excluded_qty}</TableCell>
              <TableCell>{binCounts(s.bin_counts)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  )
}

function BinSetTable({ data }: { data: BinSetPreview }) {
  return (
    <section className='flex flex-col gap-2'>
      <h3 className='font-medium'>
        {data.bin_set
          ? t('mes.map.binSetPreview', {
              code: data.bin_set.code,
              version: data.bin_set.version,
            })
          : t('mes.map.kind.binSet')}
      </h3>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t('mes.map.binCode')}</TableHead>
            <TableHead>{t('mes.map.binType')}</TableHead>
            <TableHead>{t('mes.map.binDesc')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.definitions.map((d) => (
            <TableRow key={d.bin_code}>
              <TableCell>{d.bin_code}</TableCell>
              <TableCell>
                {d.bin_type}
                {data.excluded_bin_codes.includes(d.bin_code) && (
                  <Badge variant='outline' className='ms-2'>
                    {t('mes.map.excluded')}
                  </Badge>
                )}
              </TableCell>
              <TableCell>{d.description ?? ''}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  )
}

const binCounts = (c: Record<string, number>) =>
  Object.entries(c)
    .map(([k, v]) => `${k}:${v}`)
    .join(' ')

/** 已导入坐标图（某基板某版本）的表格；时间转本地时区。 */
function MapTable({ rows }: { rows: SubstrateMap[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t('mes.map.substrate')}</TableHead>
          <TableHead>{t('mes.map.version')}</TableHead>
          <TableHead>{t('mes.map.size')}</TableHead>
          <TableHead>{t('mes.map.total')}</TableHead>
          <TableHead>{t('mes.map.good')}</TableHead>
          <TableHead>{t('mes.map.excluded')}</TableHead>
          <TableHead>{t('mes.map.binSet')}</TableHead>
          <TableHead>{t('mes.map.origin')}</TableHead>
          <TableHead>{t('mes.map.lot')}</TableHead>
          <TableHead>{t('mes.map.importedAt')}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((m) => (
          <TableRow key={m.id}>
            <TableCell>{m.code}</TableCell>
            <TableCell>
              <Badge variant='outline'>v{m.map_version}</Badge>
            </TableCell>
            <TableCell>
              {m.rows}×{m.cols}
            </TableCell>
            <TableCell>{m.total_qty}</TableCell>
            <TableCell>{m.good_qty}</TableCell>
            <TableCell>{m.excluded_qty}</TableCell>
            <TableCell>{m.bin_set_label ?? ''}</TableCell>
            <TableCell>
              {m.origin_location} / X {m.x_axis} / Y {m.y_axis}
            </TableCell>
            <TableCell>{m.lot_label ?? '—'}</TableCell>
            <TableCell>{fmtDateTime(m.created_at)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

/** 按基板编号查询坐标图，可切换版本（需要 mes.map:read）。 */
function Lookup() {
  const tk = useTenantKey()
  const can = useMesCan()
  const [text, setText] = useState('')
  const [code, setCode] = useState('')
  const [version, setVersion] = useState<number | undefined>()
  const q = useQuery({
    queryKey: ['mes', 'map', tk, 'substrate', code, version],
    queryFn: () => mapApi.bySubstrate(code, version),
    enabled: !!code,
    retry: false,
  })
  const err = q.error ? mapApiError(q.error) : null
  return (
    <section className='flex flex-col gap-2'>
      <h3 className='font-medium'>{t('mes.map.lookup')}</h3>
      <form
        className='flex gap-2'
        onSubmit={(e) => {
          e.preventDefault()
          setVersion(undefined)
          setCode(text.trim())
        }}
      >
        <Input
          className='max-w-xs'
          aria-label={t('mes.map.substrate')}
          placeholder={t('mes.map.lookupPlaceholder')}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <Button
          type='submit'
          variant='outline'
          disabled={!text.trim() || !can(MES_PERM.mapRead)}
          title={can(MES_PERM.mapRead) ? undefined : t('mes.map.noPermission')}
        >
          <Search />
          {t('mes.map.lookupBtn')}
        </Button>
      </form>
      {err && (
        <p className='text-sm text-destructive'>{mapErrorMessage(err)}</p>
      )}
      {q.data && (
        <>
          <div className='flex flex-wrap gap-1'>
            {q.data.versions.map((v) => (
              <Button
                key={v}
                size='sm'
                variant={v === q.data.map_version ? 'default' : 'outline'}
                aria-pressed={v === q.data.map_version}
                onClick={() => setVersion(v)}
              >
                v{v}
              </Button>
            ))}
          </div>
          <MapTable rows={[q.data]} />
        </>
      )}
    </section>
  )
}
