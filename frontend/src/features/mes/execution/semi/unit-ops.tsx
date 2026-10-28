/** 单元转换与芯片图页面：导入 CP / AOI 芯片图、查看良率，整批转换为芯片 / 条带 / 单颗。 */
import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Eye, FileDown, FolderOpen, Shuffle, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import {
  blockedResults,
  execApi,
  type CheckResult,
} from '@/lib/api/mes/execution'
import {
  parseDieCsv,
  semiApi,
  type ConvertBody,
  type DieMapKind,
  type UnitKind,
} from '@/lib/api/mes/semi'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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
import { Textarea } from '@/components/ui/textarea'
import { Page } from '@/components/crud'
import { enumLabel } from '@/features/mes/common/labels'
import { MES_PERM, useMesCan } from '@/features/mes/common/mes-perm'
import { RefSelect } from '@/features/mes/common/ref-select'
import { mesErrorMessage } from '@/features/mes/common/required'
import { CheckPanel, Pick } from '../shared/exec-parts'
import { DieMapDialog } from './die-map-view'
import { convertBody, type ConvertMode } from './semi-utils'

type Mode = ConvertMode
const KINDS: UnitKind[] = ['die', 'strip', 'package', 'unit']
const MAP_KINDS: DieMapKind[] = ['cp', 'aoi', 'ink']

/** 单元转换与芯片图。 */
export default function UnitOps() {
  const tk = useTenantKey()
  const qc = useQueryClient()
  const can = useMesCan()
  const [lot, setLot] = useState<{ id: string; code: string } | null>(null)
  const [view, setView] = useState<string | null>(null)
  const [mapKind, setMapKind] = useState<DieMapKind>('cp')
  const [source, setSource] = useState('')
  const [csv, setCsv] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  const [kind, setKind] = useState<UnitKind>('die')
  const [mode, setMode] = useState<Mode>('map')
  const [n, setN] = useState(1)
  const [comment, setComment] = useState('')
  const [results, setResults] = useState<CheckResult[] | null>(null)
  const [blocked, setBlocked] = useState(false)
  const [preview, setPreview] = useState<string | null>(null)
  const ctx = useQuery({
    queryKey: ['mes', 'exec', tk, 'context', lot?.id],
    queryFn: () => execApi.context(lot!.id),
    enabled: !!lot,
  })
  const wm = useQuery({
    queryKey: ['mes', 'exec', tk, 'wafer-status', lot?.id],
    queryFn: () => execApi.waferStatus(lot!.id),
    enabled: !!lot,
  })
  const maps = new Map(
    (wm.data?.slots ?? [])
      .map((s) => s.wafer)
      .filter((w) => w?.die_map)
      .map((w) => [w!.id, w!.die_map!])
  )
  const units = ctx.data?.units.filter((u) => u.status !== 'scrapped') ?? []
  const refresh = () => qc.invalidateQueries({ queryKey: ['mes'] })
  const parsed = parseDieCsv(csv)
  const loadFile = async (f?: File) => {
    if (!f) return
    setCsv(await f.text())
    setSource((s) => s || f.name)
    if (fileRef.current) fileRef.current.value = ''
  }
  const imp = useMutation({
    mutationFn: () =>
      semiApi.importDieMaps(lot!.id, {
        test_kind: mapKind,
        source: source.trim() || undefined,
        maps: parsed.maps,
      }),
    onSuccess: (r) => {
      toast.success(t('mes.semi.imported', { count: r.maps.length }))
      setCsv('')
      refresh()
    },
    onError: (e) => toast.error(mesErrorMessage(e, undefined)),
  })
  const conv = useMutation({
    mutationFn: (extra: Partial<ConvertBody>) =>
      semiApi.convert(lot!.id, {
        ...convertBody(kind, mode, n, comment),
        ...extra,
      }),
    onSuccess: (r, extra) => {
      setResults(r.results)
      setBlocked(false)
      if (extra.preview) {
        setPreview(
          t('mes.semi.previewResult', { count: r.count, bad: r.bad_dies })
        )
        return
      }
      setPreview(null)
      toast.success(t('mes.semi.converted', { count: r.count }))
      refresh()
    },
    onError: (e) => {
      const b = blockedResults(e)
      if (b) {
        setResults(b)
        setBlocked(true)
      } else toast.error(mesErrorMessage(e, undefined))
    },
  })
  const canWrite = can(MES_PERM.execWrite)
  return (
    <Page title={t('menu.mes-unit-ops')} description={t('mes.semi.unitHint')}>
      <DieMapDialog mapId={view} onClose={() => setView(null)} />
      <div className='max-w-sm'>
        <Label htmlFor='unit-ops-lot'>{t('mes.field.lot.code')}</Label>
        <RefSelect
          id='unit-ops-lot'
          target='lot'
          value={lot?.id ?? null}
          label={lot?.code ?? null}
          onChange={(id, label) => {
            setLot(id ? { id, code: label ?? '' } : null)
            setResults(null)
            setPreview(null)
          }}
        />
      </div>
      {lot && (
        <div className='grid gap-4 lg:grid-cols-2'>
          <Card className='lg:col-span-2'>
            <CardHeader>
              <CardTitle>
                {t('mes.semi.units', { count: units.length })}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('mes.exec.unit')}</TableHead>
                    <TableHead>{t('mes.exec.slot')}</TableHead>
                    <TableHead>{t('mes.field.die_map.test_kind')}</TableHead>
                    <TableHead>{t('mes.field.die_map.yield_pct')}</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {units.slice(0, 200).map((u) => {
                    const m = maps.get(u.id)
                    return (
                      <TableRow key={u.id}>
                        <TableCell className='font-mono'>
                          {u.code}
                          <span className='ms-2 text-xs text-muted-foreground'>
                            {enumLabel('track_unit_kind', u.unit_kind)} ·{' '}
                            {enumLabel('wafer_status', u.status)}
                          </span>
                        </TableCell>
                        <TableCell>{u.slot ?? '—'}</TableCell>
                        <TableCell>
                          {m ? enumLabel('die_map_kind', m.test_kind) : '—'}
                        </TableCell>
                        <TableCell className='tabular-nums'>
                          {m ? `${m.yield_pct}% (${m.good}/${m.gross})` : '—'}
                        </TableCell>
                        <TableCell className='text-end'>
                          {m && (
                            <Button
                              size='sm'
                              variant='ghost'
                              onClick={() => setView(m.id)}
                            >
                              <Eye className='size-4' />
                              {t('mes.semi.viewMap')}
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{t('mes.semi.importMap')}</CardTitle>
            </CardHeader>
            <CardContent className='space-y-3'>
              <Pick
                id='map-kind'
                label={t('mes.field.die_map.test_kind')}
                none={false}
                value={mapKind}
                onChange={(v) => setMapKind(v as DieMapKind)}
                options={MAP_KINDS.map((k) => ({
                  id: k,
                  label: enumLabel('die_map_kind', k),
                }))}
              />
              <div className='grid gap-1'>
                <Label htmlFor='map-source'>
                  {t('mes.field.die_map.source')}
                </Label>
                <Input
                  id='map-source'
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                />
              </div>
              <div className='grid gap-1'>
                <div className='flex items-center gap-2'>
                  <Label htmlFor='map-csv' className='me-auto'>
                    {t('mes.semi.csv')}
                  </Label>
                  <input
                    ref={fileRef}
                    type='file'
                    accept='.csv,.txt'
                    className='hidden'
                    onChange={(e) => loadFile(e.target.files?.[0])}
                  />
                  <Button
                    size='sm'
                    variant='outline'
                    title={t('mes.importTemplateHint')}
                    onClick={() =>
                      semiApi
                        .dieMapTemplate()
                        .catch((e) =>
                          toast.error(mesErrorMessage(e, undefined))
                        )
                    }
                  >
                    <FileDown className='size-4' />
                    {t('mes.importTemplate')}
                  </Button>
                  <Button
                    size='sm'
                    variant='outline'
                    onClick={() => fileRef.current?.click()}
                  >
                    <FolderOpen className='size-4' />
                    {t('mes.semi.csvFile')}
                  </Button>
                </div>
                <Textarea
                  id='map-csv'
                  rows={6}
                  className='font-mono text-xs'
                  placeholder={t('mes.semi.csvHint')}
                  value={csv}
                  onChange={(e) => setCsv(e.target.value)}
                />
                <p className='text-xs text-muted-foreground'>
                  {t('mes.semi.csvParsed', {
                    maps: parsed.maps.length,
                    dies: parsed.maps.reduce((a, m) => a + m.dies.length, 0),
                  })}
                  {parsed.bad.length > 0 &&
                    ` · ${t('mes.semi.csvBad', { rows: parsed.bad.slice(0, 5).join(', ') })}`}
                </p>
              </div>
              <Button
                disabled={!canWrite || !parsed.maps.length || imp.isPending}
                onClick={() => imp.mutate()}
              >
                <Upload className='size-4' />
                {t('mes.semi.import')}
              </Button>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{t('mes.semi.convert')}</CardTitle>
            </CardHeader>
            <CardContent className='space-y-3'>
              <Pick
                id='conv-kind'
                label={t('mes.semi.toKind')}
                none={false}
                value={kind}
                onChange={(v) => setKind(v as UnitKind)}
                options={KINDS.map((k) => ({
                  id: k,
                  label: enumLabel('track_unit_kind', k),
                }))}
              />
              <Pick
                id='conv-mode'
                label={t('mes.semi.mode')}
                none={false}
                value={mode}
                onChange={(v) => setMode(v as Mode)}
                options={(['map', 'split', 'assemble'] as const).map((k) => ({
                  id: k,
                  label: t(`mes.semi.modes.${k}`),
                }))}
              />
              {mode !== 'map' && (
                <div className='grid gap-1'>
                  <Label htmlFor='conv-n'>{t(`mes.semi.ratio.${mode}`)}</Label>
                  <Input
                    id='conv-n'
                    type='number'
                    min={1}
                    value={n}
                    onChange={(e) =>
                      setN(Math.max(1, Number(e.target.value) || 1))
                    }
                  />
                </div>
              )}
              <div className='grid gap-1'>
                <Label htmlFor='conv-comment'>{t('mes.exec.comment')}</Label>
                <Input
                  id='conv-comment'
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                />
              </div>
              {preview && <p className='text-sm'>{preview}</p>}
              <CheckPanel
                results={results}
                blocked={blocked}
                canOverride={can(MES_PERM.execOverride)}
                busy={conv.isPending}
                onOverride={(reason) =>
                  conv.mutate({ override: true, override_reason: reason })
                }
              />
              <div className='flex gap-2'>
                <Button
                  variant='outline'
                  disabled={conv.isPending}
                  onClick={() => conv.mutate({ preview: true })}
                >
                  {t('mes.exec.preview')}
                </Button>
                <Button
                  disabled={!canWrite || conv.isPending}
                  onClick={() => conv.mutate({})}
                >
                  <Shuffle className='size-4' />
                  {t('mes.semi.convert')}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </Page>
  )
}
