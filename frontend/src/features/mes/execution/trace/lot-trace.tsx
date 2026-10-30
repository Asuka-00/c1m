/** 批次履历、晶圆状态与配方执行记录卡片（批次操作台的页签）。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import {
  ArrowRightToLine,
  CircleCheck,
  CornerDownRight,
  GitFork,
  GitMerge,
  GitBranch,
  Inbox,
  LogIn,
  LogOut,
  PauseCircle,
  PlayCircle,
  Rocket,
  ShieldAlert,
  Square,
  Timer,
  Trash2,
  TriangleAlert,
  Undo2,
  type LucideIcon,
} from 'lucide-react'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi, type MesRow } from '@/lib/api/mes/common'
import { execApi, type WaferCell } from '@/lib/api/mes/execution'
import { checkMessage, type MsgPart } from '@/lib/backend-text'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { EmptyState } from '@/components/desc-list'
import { enumLabel, reasonLabel } from '@/features/mes/common/labels'
import { ResultBadge } from '../shared/exec-parts'

const ICON: Record<string, [LucideIcon, string]> = {
  start: [Rocket, 'bg-sky-500'],
  move_in: [LogIn, 'bg-blue-500'],
  track_in: [PlayCircle, 'bg-indigo-500'],
  track_out: [Square, 'bg-indigo-400'],
  move_out: [LogOut, 'bg-blue-400'],
  hold: [PauseCircle, 'bg-destructive'],
  release: [PlayCircle, 'bg-emerald-500'],
  scrap: [Trash2, 'bg-destructive'],
  rework: [Undo2, 'bg-amber-500'],
  branch: [GitBranch, 'bg-violet-500'],
  sub_route: [CornerDownRight, 'bg-violet-400'],
  return: [ArrowRightToLine, 'bg-violet-400'],
  complete: [CircleCheck, 'bg-emerald-600'],
  override: [ShieldAlert, 'bg-violet-600'],
  qtime: [Timer, 'bg-amber-600'],
  oos: [TriangleAlert, 'bg-amber-500'],
  split: [GitFork, 'bg-sky-600'],
  merge: [GitMerge, 'bg-violet-600'],
}

type Check = {
  type: string
  rule: string | null
  result: string
  message: string
  msg_parts?: MsgPart[]
}

function Details({ d }: { d: Record<string, unknown> }) {
  const checks = (d.checks as Check[] | undefined) ?? []
  const facts: string[] = []
  if (d.dc) facts.push(t('mes.trace.dc', { n: d.dc, oos: d.oos ?? 0 }))
  if (d.oos_action)
    facts.push(`OOS → ${enumLabel('oos_action', String(d.oos_action))}`)
  if (d.scrap) facts.push(t('mes.trace.scrap', { n: d.scrap }))
  for (const c of (d.consumed as {
    material_lot: string
    qty: number
    left: number
  }[]) ?? [])
    facts.push(`${c.material_lot} −${c.qty} (${c.left})`)
  for (const x of (d.tools as {
    tool: string
    usage: number
    max: number | null
    status: string
  }[]) ?? [])
    if (typeof x === 'object')
      facts.push(
        `${x.tool} ${x.usage}/${x.max ?? '∞'} ${enumLabel('tool_status', x.status)}`
      )
  const e10 = d.e10 as Record<string, string> | null
  if (e10?.to) facts.push(`E10 ${e10.equipment}: ${e10.from} → ${e10.to}`)
  if (d.condition) facts.push(t('mes.trace.condition', { c: d.condition }))
  if (d.route) facts.push(String(d.route))
  if (d.source) facts.push(t('mes.trace.source', { s: d.source }))
  if (d.rule && d.minutes)
    facts.push(`${d.rule}: ${d.minutes} > ${d.max} min → ${d.action}`)
  if (d.override_reason)
    facts.push(t('mes.trace.overrideReason', { r: d.override_reason }))
  if (d.reason && typeof d.reason === 'string')
    facts.push(t('mes.trace.overrideReason', { r: d.reason }))
  if (d.sampling) facts.push(String(d.sampling))
  const kids = d.children as { code: string; qty: number }[] | undefined
  if (kids?.length)
    facts.push(
      t('mes.sm.factChildren', {
        list: kids.map((c) => `${c.code} (${c.qty})`).join(', '),
      })
    )
  if (d.parent) facts.push(t('mes.sm.factParent', { code: d.parent }))
  const pc = d.priority as { from: string | null; to: string } | null
  if (pc && typeof pc === 'object' && pc.to)
    facts.push(t('mes.sm.factPriority', { from: pc.from ?? '—', to: pc.to }))
  if (d.target) facts.push(t('mes.sm.factTarget', { code: d.target }))
  const srcs = d.sources as { code: string; qty: number }[] | undefined
  if (srcs?.length)
    facts.push(
      t('mes.sm.factSources', {
        list: srcs.map((c) => `${c.code} (${c.qty})`).join(', '),
      })
    )
  return (
    <div className='space-y-1'>
      {facts.length > 0 && (
        <div className='flex flex-wrap gap-x-3 text-xs text-muted-foreground'>
          {facts.map((f, i) => (
            <span key={i}>{f}</span>
          ))}
        </div>
      )}
      {checks.length > 0 && (
        <div className='flex flex-wrap gap-1'>
          {checks.map((c, i) => (
            <span
              key={i}
              title={checkMessage(c)}
              className='inline-flex items-center gap-1 text-xs'
            >
              <ResultBadge r={c.result} />
              {c.rule ?? enumLabel('check_type', c.type)}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

/** 履历时间线（批次或晶圆）。 */
function HistoryTimeline({ rows }: { rows: MesRow[] }) {
  return (
    <ol className='relative space-y-4 border-s ps-6' data-testid='timeline'>
      {rows.map((h: MesRow) => {
        const [Icon, color] = ICON[String(h.action)] ?? [
          Square,
          'bg-muted-foreground',
        ]
        return (
          <li key={h.id} className='relative'>
            <span
              className={cn(
                'absolute -start-[37px] flex size-6 items-center justify-center rounded-full text-white ring-4 ring-background',
                color
              )}
            >
              <Icon className='size-3.5' />
            </span>
            <div className='flex flex-wrap items-baseline gap-x-3 gap-y-0.5'>
              <span className='font-medium'>
                {enumLabel('history_action', String(h.action))}
              </span>
              <span className='text-xs text-muted-foreground'>
                {fmtDateTime(String(h.at))}
              </span>
              <span className='text-xs text-muted-foreground'>
                {String(h.username ?? '')}
              </span>
            </div>
            <div className='flex flex-wrap gap-x-4 text-sm'>
              {h.step_seq != null && (
                <span>
                  {String(h.step_seq)} ·{' '}
                  {String(h.operation_label ?? '').split(' · ')[0]}
                </span>
              )}
              {!!h.equipment_label && (
                <span>{String(h.equipment_label).split(' · ')[0]}</span>
              )}
              {!!h.recipe_label && (
                <span>{String(h.recipe_label).split(' · ')[0]}</span>
              )}
              {!!h.unit_label && (
                <span className='font-mono text-xs'>
                  {String(h.unit_label)}
                </span>
              )}
              <span className='text-muted-foreground'>
                {t('mes.exec.qty')} {String(h.qty ?? '')}
              </span>
              {!!h.to_status && (
                <Badge variant='outline'>
                  {enumLabel('lot_status', String(h.to_status))}
                </Badge>
              )}
              {!!h.reason_label && <span>{reasonLabel(h.reason_label)}</span>}
              {!!h.comment && (
                <span className='text-muted-foreground'>
                  “{String(h.comment)}”
                </span>
              )}
            </div>
            {!!h.details && (
              <Details d={h.details as Record<string, unknown>} />
            )}
          </li>
        )
      })}
    </ol>
  )
}

const WAFER_COLOR: Record<string, string> = {
  waiting: 'bg-sky-100 border-sky-300 text-sky-900',
  processing: 'bg-indigo-500 border-indigo-600 text-white',
  rework: 'bg-amber-400 border-amber-500 text-amber-950',
  completed: 'bg-emerald-500 border-emerald-600 text-white',
  scrapped: 'bg-destructive border-destructive text-white',
}

/** 晶圆状态：按槽位显示晶圆状态，点击晶圆查看晶圆履历。 */
export function WaferStatusCard({ lotId }: { lotId: string }) {
  const tk = useTenantKey()
  const [pick, setPick] = useState<WaferCell | null>(null)
  const map = useQuery({
    queryKey: ['mes', 'exec', tk, lotId, 'wafer-status'],
    queryFn: () => execApi.waferStatus(lotId),
  })
  const hist = useQuery({
    queryKey: ['mes', 'exec', tk, pick?.id, 'wafer-history'],
    queryFn: () => execApi.waferHistory(pick!.id),
    enabled: !!pick,
  })
  const m = map.data
  if (!m) return null
  if (!m.slots.some((x) => x.wafer) && m.units.length === 0)
    return <EmptyState icon={Inbox}>{t('common.noResults')}</EmptyState>
  const cell = (w: WaferCell | null, label: string, key: string | number) => (
    <button
      key={key}
      type='button'
      disabled={!w}
      title={w ? `${w.code} · ${enumLabel('wafer_status', w.status)}` : label}
      onClick={() => w && setPick(w)}
      data-testid={w ? 'wafer-cell' : 'empty-slot'}
      className={cn(
        'flex h-9 flex-col items-center justify-center rounded border text-[10px] leading-tight',
        w
          ? (WAFER_COLOR[w.status] ?? 'bg-muted') +
              ' hover:ring-2 hover:ring-ring'
          : 'border-dashed text-muted-foreground'
      )}
    >
      <span className='font-medium'>{label}</span>
      {w && (
        <span className='max-w-full truncate px-0.5'>{w.code.slice(-4)}</span>
      )}
    </button>
  )
  return (
    <Card>
      <CardHeader className='pb-2'>
        <CardTitle className='flex flex-wrap items-center gap-2 text-base'>
          {t('mes.wstatus.title')}
          {m.carrier && <Badge variant='outline'>{m.carrier}</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className='space-y-3'>
        <div
          className='grid grid-cols-5 gap-1.5 sm:grid-cols-10 lg:grid-cols-13'
          data-testid='wafer-status'
        >
          {m.slots.map((x) => cell(x.wafer, String(x.slot), x.slot))}
          {m.units.map((w) => cell(w, '—', w.id))}
        </div>
        <div className='flex flex-wrap gap-3 text-xs text-muted-foreground'>
          {Object.keys(WAFER_COLOR).map((k) => (
            <span key={k} className='inline-flex items-center gap-1'>
              <span className={cn('size-3 rounded border', WAFER_COLOR[k])} />
              {enumLabel('wafer_status', k)}
            </span>
          ))}
        </div>
      </CardContent>
      <Dialog open={!!pick} onOpenChange={(o) => !o && setPick(null)}>
        <DialogContent className='max-h-[85vh] overflow-y-auto sm:max-w-2xl'>
          <DialogHeader>
            <DialogTitle>
              {t('mes.wstatus.history', { code: pick?.code ?? '' })}
            </DialogTitle>
          </DialogHeader>
          {hist.data && hist.data.length === 0 && (
            <p className='text-muted-foreground'>{t('mes.trace.empty')}</p>
          )}
          <HistoryTimeline rows={hist.data ?? []} />
        </DialogContent>
      </Dialog>
    </Card>
  )
}

/** 参数规格行（Track In 时快照）。 */
interface SpecRow {
  code: string
  name?: string
  target?: number | null
  lsl?: number | null
  usl?: number | null
  uom?: string | null
}

const firstLabel = (v: unknown) => String(v ?? '').split(' · ')[0] || '—'
const num = (v: unknown) => (v === null || v === undefined ? '—' : String(v))

/** 配方执行记录：每次上机的配方版本、设备、腔体，点开查看参数快照与参数规格。 */
export function RecipeRunCard({ lotId }: { lotId: string }) {
  const tk = useTenantKey()
  const [pick, setPick] = useState<MesRow | null>(null)
  const runs = useQuery({
    queryKey: ['mes', 'lot_recipe_run', 'trace', tk, lotId],
    queryFn: () =>
      mesApi.list('lot_recipe_run', {
        lot: lotId,
        sort_by: 'track_in_at',
        sort_order: 'desc',
        page_size: 100,
      }),
  })
  const rows = runs.data?.data ?? []
  if (runs.isLoading) return null
  if (rows.length === 0)
    return <EmptyState icon={Inbox}>{t('common.noResults')}</EmptyState>
  const f = (k: string) => t(`mes.field.lot_recipe_run.${k}`)
  const params = Object.entries(
    (pick?.params as Record<string, unknown> | null) ?? {}
  )
  const specs = (pick?.param_specs as SpecRow[] | null) ?? []
  return (
    <Card>
      <CardHeader className='pb-2'>
        <CardTitle className='text-base'>
          {t('mes.entity.lot_recipe_run')}
        </CardTitle>
      </CardHeader>
      <CardContent className='overflow-x-auto'>
        <Table data-testid='recipe-runs'>
          <TableHeader>
            <TableRow>
              <TableHead>{f('track_in_at')}</TableHead>
              <TableHead>{f('operation')}</TableHead>
              <TableHead>{f('equipment')}</TableHead>
              <TableHead>{f('recipe')}</TableHead>
              <TableHead>{f('chambers')}</TableHead>
              <TableHead>{f('track_out_at')}</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={String(r.id)}>
                <TableCell>{fmtDateTime(String(r.track_in_at))}</TableCell>
                <TableCell>{firstLabel(r.operation_label)}</TableCell>
                <TableCell>{firstLabel(r.equipment_label)}</TableCell>
                <TableCell>
                  {r.recipe_label
                    ? `${firstLabel(r.recipe_label)} v${num(r.recipe_version)}`
                    : '—'}
                </TableCell>
                <TableCell>{String(r.chambers ?? '') || '—'}</TableCell>
                <TableCell>
                  {r.track_out_at ? (
                    fmtDateTime(String(r.track_out_at))
                  ) : (
                    <Badge variant='outline'>{t('mes.rrun.running')}</Badge>
                  )}
                </TableCell>
                <TableCell className='text-right'>
                  <Button
                    size='sm'
                    variant='outline'
                    onClick={() => setPick(r)}
                    data-testid='recipe-run-params'
                  >
                    {t('mes.rrun.view')}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
      <Dialog open={!!pick} onOpenChange={(o) => !o && setPick(null)}>
        <DialogContent className='max-h-[85vh] overflow-y-auto sm:max-w-2xl'>
          <DialogHeader>
            <DialogTitle>
              {t('mes.rrun.title', {
                recipe: firstLabel(pick?.recipe_label),
                version: num(pick?.recipe_version),
              })}
            </DialogTitle>
          </DialogHeader>
          <h4 className='text-sm font-medium'>{f('params')}</h4>
          {params.length === 0 ? (
            <p className='text-sm text-muted-foreground'>
              {t('mes.rrun.noParams')}
            </p>
          ) : (
            <Table data-testid='recipe-run-param-table'>
              <TableBody>
                {params.map(([k, v]) => (
                  <TableRow key={k}>
                    <TableCell className='font-mono'>{k}</TableCell>
                    <TableCell>
                      {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {specs.length > 0 && (
            <>
              <h4 className='text-sm font-medium'>{f('param_specs')}</h4>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('mes.field.param_spec.code')}</TableHead>
                    <TableHead>{t('mes.field.param_spec.target')}</TableHead>
                    <TableHead>{t('mes.field.param_spec.lsl')}</TableHead>
                    <TableHead>{t('mes.field.param_spec.usl')}</TableHead>
                    <TableHead>{t('mes.field.param_spec.uom')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {specs.map((x) => (
                    <TableRow key={x.code}>
                      <TableCell>
                        {x.code}
                        {x.name ? ` · ${x.name}` : ''}
                      </TableCell>
                      <TableCell>{num(x.target)}</TableCell>
                      <TableCell>{num(x.lsl)}</TableCell>
                      <TableCell>{num(x.usl)}</TableCell>
                      <TableCell>{x.uom ?? '—'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </>
          )}
        </DialogContent>
      </Dialog>
    </Card>
  )
}

/** 批次履历时间线：每个动作的时间、操作人、工步、设备、
 *  配方、数量、原因与检查结果。 */
export function LotHistoryCard({ lotId }: { lotId: string }) {
  const tk = useTenantKey()
  const hist = useQuery({
    queryKey: ['mes', 'lot_history', 'trace', tk, lotId],
    queryFn: () =>
      mesApi.list('lot_history', {
        lot: lotId,
        sort_by: 'at',
        sort_order: 'desc',
        page_size: 100,
      }),
  })
  const rows = hist.data?.data ?? []
  return (
    <Card>
      <CardContent className='pt-6'>
        {rows.length === 0 && !hist.isLoading && (
          <p className='text-muted-foreground'>{t('mes.trace.empty')}</p>
        )}
        <HistoryTimeline rows={rows} />
      </CardContent>
    </Card>
  )
}
