/** 标签打印页面：批次 / 载具条码与二维码，生成可打印页面。 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Printer } from 'lucide-react'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi, type MesRow } from '@/lib/api/mes/common'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  DataTable,
  Page,
  useListParams,
  type FilterDef,
} from '@/components/crud'
import { enumLabel } from '@/features/mes/common/labels'
import { printHtml, type CodeKind, type LabelData } from './label-utils'

type Kind = 'lot' | 'carrier'
const LOT_STATUS = [
  'waiting',
  'moved_in',
  'running',
  'tracked_out',
  'completed',
  'stored',
]
const CARRIER_STATUS = ['available', 'in_use', 'dirty', 'hold', 'retired']
const s = (v: unknown) => (v == null ? '' : String(v))

/** 行 -> 标签数据。 */
function toLabel(kind: Kind, r: MesRow, hot: Set<string>): LabelData {
  if (kind === 'carrier')
    return {
      code: s(r.code),
      title: s(r.name),
      lines: [s(r.carrier_type_label)],
    }
  return {
    code: s(r.code),
    title: s(r.product_label),
    lines: [
      `${t('mes.label.qty')} ${s(r.qty)} · ${s(r.current_step_label)}`,
      s(r.work_order_label),
    ],
    hot: hot.has(s(r.priority_id)),
  }
}

/** 标签打印。 */
export default function LabelPrint() {
  const tk = useTenantKey()
  const [kind, setKind] = useState<Kind>('lot')
  const [code, setCode] = useState<CodeKind>('both')
  const [picked, setPicked] = useState<Record<string, MesRow>>({})
  const prio = useQuery({
    queryKey: ['mes', 'lot_priority', tk, 'all'],
    queryFn: () => mesApi.list('lot_priority', { page_size: 100 }),
  })
  const hot = useMemo(
    () =>
      new Set((prio.data?.data ?? []).filter((p) => p.is_hot).map((p) => p.id)),
    [prio.data]
  )
  const filters: FilterDef[] = [
    { type: 'text', name: 'q', placeholder: t('mes.label.search') },
    kind === 'lot'
      ? {
          type: 'select',
          name: 'lot_status',
          label: t('mes.label.allStatus'),
          options: LOT_STATUS.map((v) => ({
            value: v,
            label: enumLabel('lot_status', v),
          })),
        }
      : {
          type: 'select',
          name: 'status_code',
          label: t('mes.label.allStatus'),
          options: CARRIER_STATUS.map((v) => ({
            value: v,
            label: enumLabel('asset_status', v),
          })),
        },
  ]
  const lp = useListParams(filters)
  const q = useQuery({
    queryKey: ['mes', kind, tk, 'labels', lp.query],
    queryFn: () => mesApi.list(kind, lp.query),
  })
  const rows = q.data?.data ?? []
  const chosen = Object.values(picked)
  const print = async () => {
    const html = await printHtml(
      chosen.map((r) => toLabel(kind, r, hot)),
      code
    )
    const w = window.open('', '_blank')
    if (!w) return
    w.document.write(html)
    w.document.close()
    w.focus()
    w.print()
  }
  const allOnPage = rows.length > 0 && rows.every((r) => !!picked[r.id])
  return (
    <Page title={t('menu.mes-label-print')} description={t('mes.label.hint')}>
      <div className='flex flex-wrap items-center gap-3'>
        <Select
          value={kind}
          onValueChange={(v) => {
            setKind(v as Kind)
            setPicked({})
          }}
        >
          <SelectTrigger className='max-w-72 min-w-36' data-testid='label-kind'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(['lot', 'carrier'] as const).map((k) => (
              <SelectItem key={k} value={k}>
                {t(`mes.label.kind.${k}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={code} onValueChange={(v) => setCode(v as CodeKind)}>
          <SelectTrigger className='max-w-72 min-w-40'>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(['both', 'barcode', 'qr'] as const).map((k) => (
              <SelectItem key={k} value={k}>
                {t(`mes.label.code.${k}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button disabled={!chosen.length} onClick={print} data-testid='print'>
          <Printer className='size-4' />
          {t('mes.label.print', { n: chosen.length })}
        </Button>
      </div>
      <DataTable
        rows={rows}
        total={q.data?.count ?? 0}
        params={lp}
        filters={filters}
        loading={q.isLoading}
        rowKey={(r) => r.id}
        columns={[
          {
            header: '',
            headerNode: (
              <Checkbox
                aria-label={t('mes.label.pickAll')}
                checked={allOnPage}
                onCheckedChange={(v) =>
                  setPicked((p) => {
                    const n = { ...p }
                    for (const r of rows) {
                      if (v) n[r.id] = r
                      else delete n[r.id]
                    }
                    return n
                  })
                }
              />
            ),
            cell: (r) => (
              <Checkbox
                aria-label={s(r.code)}
                checked={!!picked[r.id]}
                onCheckedChange={(v) =>
                  setPicked((p) => {
                    const n = { ...p }
                    if (v) n[r.id] = r
                    else delete n[r.id]
                    return n
                  })
                }
              />
            ),
          },
          {
            header: t('mes.label.codeCol'),
            sortKey: 'code',
            cell: (r) => <span className='font-mono'>{s(r.code)}</span>,
          },
          {
            header: t('mes.label.info'),
            cell: (r) =>
              kind === 'lot'
                ? `${s(r.product_label)} · ${s(r.current_step_label)}`
                : `${s(r.name)} · ${s(r.carrier_type_label)}`,
          },
          {
            header: t('mes.label.status'),
            cell: (r) =>
              kind === 'lot'
                ? enumLabel('lot_status', s(r.lot_status))
                : enumLabel('asset_status', s(r.status_code)),
          },
        ]}
      />
    </Page>
  )
}
