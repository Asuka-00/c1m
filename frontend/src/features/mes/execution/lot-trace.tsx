/** 批次履历页面（时间线 + 谱系）。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useSearch } from '@tanstack/react-router'
import { fmtDateTime, t } from '@/i18n'
import {
  ArrowRightToLine,
  CircleCheck,
  CornerDownRight,
  GitFork,
  GitMerge,
  Gauge,
  GitBranch,
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
import { Label } from '@/components/ui/label'
import { Page } from '@/components/crud'
import { enumLabel, reasonLabel } from '@/features/mes/common/labels'
import { RefSelect } from '@/features/mes/common/ref-select'
import { ResultBadge } from './exec-parts'
import { GenealogyList } from './split-merge'

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
              title={c.message}
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

/** 晶圆图：按槽位显示晶圆状态，点击晶圆查看晶圆履历。 */
export function WaferMapCard({ lotId }: { lotId: string }) {
  const tk = useTenantKey()
  const [pick, setPick] = useState<WaferCell | null>(null)
  const map = useQuery({
    queryKey: ['mes', 'exec', tk, lotId, 'wafer-map'],
    queryFn: () => execApi.waferMap(lotId),
  })
  const hist = useQuery({
    queryKey: ['mes', 'exec', tk, pick?.id, 'wafer-history'],
    queryFn: () => execApi.waferHistory(pick!.id),
    enabled: !!pick,
  })
  const m = map.data
  if (!m || (!m.slots.some((x) => x.wafer) && m.units.length === 0)) return null
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
          {t('mes.wmap.title')}
          {m.carrier && <Badge variant='outline'>{m.carrier}</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className='space-y-3'>
        <div
          className='grid grid-cols-5 gap-1.5 sm:grid-cols-10 lg:grid-cols-13'
          data-testid='wafer-map'
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
              {t('mes.wmap.history', { code: pick?.code ?? '' })}
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

/** 批次履历时间线：每个动作的时间、操作人、工步、设备、
 *  配方、数量、原因与检查结果。 */
export default function LotTracePage() {
  const search = useSearch({ strict: false }) as Record<string, unknown>
  const nav = useNavigate()
  const lotId = (search.lot as string) || ''
  const tk = useTenantKey()
  const lot = useQuery({
    queryKey: ['mes', 'lot', 'one', tk, lotId],
    queryFn: () => mesApi.get('lot', lotId),
    enabled: !!lotId,
  })
  const hist = useQuery({
    queryKey: ['mes', 'lot_history', 'trace', tk, lotId],
    queryFn: () =>
      mesApi.list('lot_history', {
        lot: lotId,
        sort_by: 'at',
        sort_order: 'desc',
        page_size: 100,
      }),
    enabled: !!lotId,
  })
  const gen = useQuery({
    queryKey: ['mes', 'exec', tk, lotId, 'genealogy'],
    queryFn: () => execApi.context(lotId),
    enabled: !!lotId,
  })
  const rows = hist.data?.data ?? []
  return (
    <Page
      title={t('menu.mes-lot-trace')}
      description={t('mes.trace.hint')}
      actions={
        lotId && (
          <Button variant='outline' asChild>
            <Link
              to='/$'
              params={{ _splat: 'mes/lot-console' }}
              search={{ lot: lotId } as never}
            >
              <Gauge className='size-4' />
              {t('menu.mes-lot-console')}
            </Link>
          </Button>
        )
      }
    >
      <div className='flex max-w-xl items-center gap-2'>
        <Label className='shrink-0'>{t('mes.entity.lot')}</Label>
        <RefSelect
          target='lot'
          value={lotId || null}
          label={lot.data ? String(lot.data.code) : null}
          onChange={(id) =>
            nav({
              to: '/$',
              params: { _splat: 'mes/lot-history' },
              search: (id
                ? { tab: 'mes-lot-trace', lot: id }
                : { tab: 'mes-lot-trace' }) as never,
            })
          }
        />
        {lot.data && (
          <>
            <Badge variant='outline'>
              {enumLabel('lot_status', String(lot.data.lot_status))}
            </Badge>
            {!!lot.data.on_hold && (
              <Badge variant='destructive'>{t('mes.exec.onHold')}</Badge>
            )}
          </>
        )}
      </div>
      {!lotId && (
        <p className='text-muted-foreground'>{t('mes.exec.pickLot')}</p>
      )}
      {lotId && (gen.data?.sm?.genealogy.length ?? 0) > 0 && (
        <Card>
          <CardHeader className='pb-2'>
            <CardTitle className='text-base'>{t('mes.sm.genealogy')}</CardTitle>
          </CardHeader>
          <CardContent>
            <GenealogyList
              lotId={lotId}
              links={gen.data?.sm?.genealogy ?? []}
            />
          </CardContent>
        </Card>
      )}
      {lotId && <WaferMapCard lotId={lotId} />}
      {lotId && (
        <Card>
          <CardContent className='pt-6'>
            {rows.length === 0 && !hist.isLoading && (
              <p className='text-muted-foreground'>{t('mes.trace.empty')}</p>
            )}
            <HistoryTimeline rows={rows} />
          </CardContent>
        </Card>
      )}
    </Page>
  )
}
