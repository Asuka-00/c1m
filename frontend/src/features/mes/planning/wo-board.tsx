/** 工单进度看板：完工进度、在制分布与交期预警。 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { useTenantKey } from '@/lib/api/hooks'
import { woApi, type WoBoardRow, type WoRisk } from '@/lib/api/mes/planning'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  DataTable,
  Page,
  clientList,
  useListParams,
  type FilterDef,
} from '@/components/crud'
import { enumLabel } from '@/features/mes/common/labels'
import { RefLink } from '@/features/mes/common/ref-link'

const RISKS: WoRisk[] = ['overdue', 'at_risk', 'ok', 'none', 'done']
const TONE: Record<WoRisk, string> = {
  overdue: 'bg-red-600 text-white',
  at_risk: 'bg-amber-500 text-white',
  ok: 'bg-emerald-600 text-white',
  none: 'bg-muted text-muted-foreground',
  done: 'bg-sky-600 text-white',
}

/** 进度条：已完工（实色）+ 在制（浅色）占计划数量。 */
function Bar({ r }: { r: WoBoardRow }) {
  const p = r.planned || 1
  const done = Math.min(100, (r.completed / p) * 100)
  const wip = Math.min(100 - done, (r.wip / p) * 100)
  return (
    <div className='flex min-w-40 items-center gap-2'>
      <div className='flex h-2 flex-1 overflow-hidden rounded bg-muted'>
        <div className='bg-emerald-600' style={{ width: `${done}%` }} />
        <div className='bg-sky-400' style={{ width: `${wip}%` }} />
      </div>
      <span className='w-12 text-right text-xs tabular-nums'>
        {Math.round(r.progress * 100)}%
      </span>
    </div>
  )
}

/** 工单进度看板。 */
export default function WoBoard() {
  const tk = useTenantKey()
  const [warn, setWarn] = useState<number>()
  const q = useQuery({
    queryKey: ['mes', 'wo', tk, 'board', warn],
    queryFn: () => woApi.board(warn),
    refetchInterval: 60_000,
  })
  const all = useMemo(() => q.data ?? [], [q.data])
  const filters: FilterDef[] = [
    { type: 'text', name: 'q', placeholder: t('mes.woBoard.search') },
    {
      type: 'select',
      name: 'risk',
      label: t('mes.woBoard.allRisks'),
      options: RISKS.map((v) => ({
        value: v,
        label: t(`mes.woBoard.risk.${v}`),
      })),
    },
  ]
  const lp = useListParams(filters)
  const view = clientList(all, lp, {
    text: (r) => `${r.code} ${r.product ?? ''}`,
    match: { risk: (r, v) => r.risk === v },
  })
  const n = (k: WoRisk) => all.filter((r) => r.risk === k).length
  return (
    <Page title={t('menu.mes-wo-board')} description={t('mes.woBoard.hint')}>
      <div className='flex flex-wrap items-center gap-3 text-sm'>
        {(['overdue', 'at_risk'] as const).map((k) => (
          <Badge key={k} className={TONE[k]}>
            {t(`mes.woBoard.risk.${k}`)} {n(k)}
          </Badge>
        ))}
        <label className='flex items-center gap-2'>
          {t('mes.woBoard.warnDays')}
          <Input
            type='number'
            min={0}
            max={60}
            className='w-20'
            value={warn ?? ''}
            placeholder={t('mes.woBoard.ruleDefault')}
            onChange={(e) =>
              setWarn(
                e.target.value === ''
                  ? undefined
                  : Math.max(0, Number(e.target.value))
              )
            }
          />
        </label>
      </div>
      <DataTable
        rows={view.rows}
        total={view.total}
        params={lp}
        filters={filters}
        loading={q.isLoading}
        rowKey={(r) => r.id}
        columns={[
          {
            header: t('mes.woBoard.code'),
            sortKey: 'code',
            cell: (r) => (
              <RefLink target='work_order' id={r.id} label={r.code} />
            ),
          },
          { header: t('mes.woBoard.product'), cell: (r) => r.product },
          {
            header: t('mes.woBoard.status'),
            cell: (r) => enumLabel('wo_status', r.status),
          },
          {
            header: t('mes.woBoard.qty'),
            className: 'text-right tabular-nums whitespace-nowrap',
            cell: (r) =>
              `${r.completed} / ${r.wip} / ${r.scrapped} / ${r.planned}`,
          },
          {
            header: t('mes.woBoard.progress'),
            sortKey: 'progress',
            cell: (r) => <Bar r={r} />,
          },
          {
            header: t('mes.woBoard.wipByOp'),
            cell: (r) =>
              r.wip_by_op.map((o) => `${o.operation}:${o.qty}`).join('  '),
          },
          {
            header: t('mes.woBoard.due'),
            sortKey: 'due_date',
            cell: (r) =>
              r.due_date
                ? `${r.due_date} (${t('mes.woBoard.daysLeft', { n: r.days_left ?? 0 })})`
                : '—',
          },
          {
            header: t('mes.woBoard.riskCol'),
            cell: (r) => (
              <Badge className={TONE[r.risk]}>
                {t(`mes.woBoard.risk.${r.risk}`)}
              </Badge>
            ),
          },
        ]}
      />
    </Page>
  )
}
