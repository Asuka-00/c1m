import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useSearch } from '@tanstack/react-router'
import { fmtDateTime, t } from '@/i18n'
import {
  ArrowRightToLine,
  CircleCheck,
  CornerDownRight,
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
import { mesApi, type MesRow } from '@/lib/api/mes'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Page } from '@/components/crud'
import { ResultBadge } from './exec-parts'
import { enumLabel } from './labels'
import { RefSelect } from './ref-select'

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

/** Lot history timeline: every action with time, user, step, equipment,
 *  recipe, qty, reason and check results. */
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
              params: { _splat: 'mes/lot-trace' },
              search: (id ? { lot: id } : {}) as never,
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
      {lotId && (
        <Card>
          <CardContent className='pt-6'>
            {rows.length === 0 && !hist.isLoading && (
              <p className='text-muted-foreground'>{t('mes.trace.empty')}</p>
            )}
            <ol
              className='relative space-y-4 border-s ps-6'
              data-testid='timeline'
            >
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
                        {String(h.user_email ?? '')}
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
                      {!!h.reason_label && (
                        <span>{String(h.reason_label)}</span>
                      )}
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
          </CardContent>
        </Card>
      )}
    </Page>
  )
}
