/** 坐标图导入（P1 / F1）：上传 CSV → 预览逐行报错 → 确认导入；下方表格查看已导入的各基板版本。 */
import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { Upload } from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import { mapApi, type MapPreview } from '@/lib/api/mes/map'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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

const TYPES = ['good', 'fail', 'edge'] as const

/** 坐标图导入页面。 */
export default function MapImport() {
  const tk = useTenantKey()
  const qc = useQueryClient()
  const can = useMesCan()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<MapPreview | null>(null)
  const listKey = ['mes', 'map', tk, 'list']
  const list = useQuery({ queryKey: listKey, queryFn: mapApi.list })

  const check = useMutation({
    mutationFn: mapApi.preview,
    onSuccess: setPreview,
    onError: () => toast.error(t('mes.map.previewFailed')),
  })
  const commit = useMutation({
    mutationFn: mapApi.commit,
    onSuccess: (maps) => {
      toast.success(t('mes.map.imported', { n: maps.length }))
      setFile(null)
      setPreview(null)
      if (input.current) input.current.value = ''
      void qc.invalidateQueries({ queryKey: listKey })
    },
    onError: () => toast.error(t('mes.map.importFailed')),
  })

  const pick = (f: File | null) => {
    setFile(f)
    setPreview(null)
    if (f) check.mutate(f)
  }
  const ok = !!preview && !preview.file_error && !preview.errors.length

  return (
    <Page title={t('mes.map.title')} description={t('mes.map.description')}>
      <div className='flex flex-wrap items-center gap-2'>
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
          disabled={!can(MES_PERM.mapImport)}
        >
          <Upload />
          {t('mes.map.chooseFile')}
        </Button>
        {file && (
          <span className='text-sm text-muted-foreground'>{file.name}</span>
        )}
        <Button
          className='ms-auto'
          disabled={
            !ok || !file || commit.isPending || !can(MES_PERM.mapImport)
          }
          onClick={() => file && commit.mutate(file)}
        >
          {t('mes.map.confirm')}
        </Button>
      </div>

      {preview?.file_error && (
        <Alert variant='destructive'>
          <AlertTitle>{t('mes.map.fileError')}</AlertTitle>
          <AlertDescription>
            {t(`mes.map.fileErrors.${preview.file_error}`, {
              set: preview.header.bin_definition_set ?? '',
              version: preview.header.bin_definition_version ?? '',
            })}
          </AlertDescription>
        </Alert>
      )}

      {preview && !preview.file_error && (
        <section className='flex flex-col gap-2'>
          <h3 className='font-medium'>
            {t('mes.map.previewTitle', {
              rows: preview.total_rows,
              errors: preview.errors.length,
            })}
          </h3>
          {preview.errors.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('mes.map.rowNo')}</TableHead>
                  <TableHead>{t('mes.map.problem')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {preview.errors.map((e) => (
                  <TableRow key={`${e.row_no}-${e.code}`}>
                    <TableCell
                      title={t('mes.map.fileLine', { n: e.file_line })}
                    >
                      {e.row_no}
                    </TableCell>
                    <TableCell>
                      {t(`mes.map.errors.${e.code}`, { value: e.value })}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <SummaryTable rows={preview.substrates} />
          )}
        </section>
      )}

      <section className='flex flex-col gap-2'>
        <h3 className='font-medium'>{t('mes.map.listTitle')}</h3>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('mes.map.substrate')}</TableHead>
              <TableHead>{t('mes.map.version')}</TableHead>
              <TableHead>{t('mes.map.size')}</TableHead>
              {TYPES.map((k) => (
                <TableHead key={k}>{t(`mes.map.binType.${k}`)}</TableHead>
              ))}
              <TableHead>{t('mes.map.binSet')}</TableHead>
              <TableHead>{t('mes.map.origin')}</TableHead>
              <TableHead>{t('mes.map.file')}</TableHead>
              <TableHead>{t('mes.map.importedAt')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(list.data ?? []).map((m) => (
              <TableRow key={m.id}>
                <TableCell>{m.substrate_id}</TableCell>
                <TableCell>
                  <Badge variant='outline'>v{m.version}</Badge>
                </TableCell>
                <TableCell>
                  {m.rows}×{m.cols}
                </TableCell>
                {TYPES.map((k) => (
                  <TableCell key={k}>{m.by_type[k] ?? 0}</TableCell>
                ))}
                <TableCell>
                  {m.bin_set} v{m.bin_set_version}
                </TableCell>
                <TableCell>
                  {m.origin_location} / X {m.x_axis} / Y {m.y_axis}
                </TableCell>
                <TableCell>{m.file_name}</TableCell>
                <TableCell>{fmtDateTime(m.imported_at)}</TableCell>
              </TableRow>
            ))}
            {!list.data?.length && (
              <TableRow>
                <TableCell
                  colSpan={10}
                  className='text-center text-muted-foreground'
                >
                  {t('mes.map.empty')}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </section>
    </Page>
  )
}

/** 预览通过时按基板汇总。 */
function SummaryTable({ rows }: { rows: MapPreview['substrates'] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t('mes.map.substrate')}</TableHead>
          <TableHead>{t('mes.map.size')}</TableHead>
          {TYPES.map((k) => (
            <TableHead key={k}>{t(`mes.map.binType.${k}`)}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((s) => (
          <TableRow key={s.substrate_id}>
            <TableCell>{s.substrate_id}</TableCell>
            <TableCell>
              {s.rows}×{s.cols}
            </TableCell>
            {TYPES.map((k) => (
              <TableCell key={k}>{s.by_type[k] ?? 0}</TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
