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
  clientList,
  useListParams,
  type FilterDef,
} from '@/components/crud'
import { enumLabel } from '@/features/mes/common/labels'
import { printHtml, type CodeKind, type LabelData } from './label-utils'

type Kind = 'lot' | 'carrier'
const ACTIVE = ['waiting', 'moved_in', 'running', 'tracked_out', 'completed']
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
  const [picked, setPicked] = useState<Record<string, boolean>>({})
  const q = useQuery({
    queryKey: ['mes', kind, tk, 'labels'],
    queryFn: () => mesApi.list(kind, { page_size: 100 }),
  })
  const prio = useQuery({
    queryKey: ['mes', 'lot_priority', tk, 'all'],
    queryFn: () => mesApi.list('lot_priority', { page_size: 100 }),
  })
  const hot = useMemo(
    () =>
      new Set((prio.data?.data ?? []).filter((p) => p.is_hot).map((p) => p.id)),
    [prio.data]
  )
  const all = useMemo(
    () =>
      (q.data?.data ?? []).filter(
        (r) => kind === 'carrier' || ACTIVE.includes(s(r.lot_status))
      ),
    [q.data, kind]
  )
  const filters: FilterDef[] = [
    { type: 'text', name: 'q', placeholder: t('mes.label.search') },
    kind === 'lot'
      ? {
          type: 'select',
          name: 'lot_status',
          label: t('mes.label.allStatus'),
          options: ACTIVE.map((v) => ({
            value: v,
            label: enumLabel('lot_status', v),
          })),
        }
      : {
          type: 'select',
          name: 'carrier_status',
          label: t('mes.label.allStatus'),
          options: [...new Set(all.map((r) => s(r.carrier_status)))]
            .filter(Boolean)
            .map((v) => ({ value: v, label: enumLabel('carrier_status', v) })),
        },
  ]
  const lp = useListParams(filters)
  const view = clientList(all, lp, {
    text: (r) => `${s(r.code)} ${s(r.product_label)} ${s(r.name)}`,
  })
  const chosen = all.filter((r) => picked[r.id])
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
  const allOnPage = view.rows.length > 0 && view.rows.every((r) => picked[r.id])
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
          <SelectTrigger className='w-36' data-testid='label-kind'>
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
          <SelectTrigger className='w-40'>
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
        rows={view.rows}
        total={view.total}
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
                  setPicked((p) => ({
                    ...p,
                    ...Object.fromEntries(view.rows.map((r) => [r.id, !!v])),
                  }))
                }
              />
            ),
            cell: (r) => (
              <Checkbox
                aria-label={s(r.code)}
                checked={!!picked[r.id]}
                onCheckedChange={(v) =>
                  setPicked((p) => ({ ...p, [r.id]: !!v }))
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
                : enumLabel('carrier_status', s(r.carrier_status)),
          },
        ]}
      />
    </Page>
  )
}
