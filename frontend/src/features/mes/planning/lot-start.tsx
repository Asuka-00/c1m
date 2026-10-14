/** 开批向导页面。 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearch } from '@tanstack/react-router'
import { t } from '@/i18n'
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Loader2,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi, type MesRow } from '@/lib/api/mes/common'
import { woApi, type StartPlan } from '@/lib/api/mes/planning'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Page } from '@/components/crud'
import { IconButton } from '@/components/icon-button'
import { cellValue } from '@/features/mes/common/cells'
import { CustomerFields, FieldMsg } from '@/features/mes/common/customer'
import {
  customerBody,
  type CustomerDraft,
  customerErrors,
  emptyCustomer,
  ownershipText,
} from '@/features/mes/common/customer-fields'
import { RefSelect } from '@/features/mes/common/ref-select'
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesEntity } from '@/features/mes/common/use-mes-meta'
import { type LotFieldErrors, startFieldErrors } from './start-errors'
import { WoProgress } from './wo-actions'

type LotDraft = {
  qty: number
  carrier_id: string | null
  carrier_label: string | null
  slots: string
  source_ref: string
} & CustomerDraft

/** 工单选择列表最多显示条数（其余通过关键字缩小范围）。 */
const WO_SHOW = 20

/** "1-3,7" -> [1,2,3,7]；格式错误时返回 null。 */
function parseSlots(s: string): number[] | null {
  const out: number[] = []
  for (const part of s
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean)) {
    const m = /^(\d+)(?:\s*-\s*(\d+))?$/.exec(part)
    if (!m) return null
    const a = Number(m[1])
    const b = m[2] ? Number(m[2]) : a
    if (b < a) return null
    for (let k = a; k <= b; k++) out.push(k)
  }
  return out
}
const range = (n: number) => (n > 0 ? `1-${n}` : '')

function Steps({ step }: { step: number }) {
  return (
    <ol className='flex flex-wrap gap-2 text-sm' data-testid='wizard-steps'>
      {[1, 2, 3].map((n) => (
        <li
          key={n}
          className={cn(
            'flex items-center gap-2 rounded-full border px-3 py-1',
            n === step && 'border-primary bg-primary text-primary-foreground',
            n < step && 'border-primary text-primary'
          )}
        >
          <span className='font-semibold'>{n}</span>
          {t(`mes.start.step${n}`)}
        </li>
      ))}
    </ol>
  )
}

/** 三步开批向导：选择工单 -> 拆分批次并分配载具 -> 确认。 */
export default function LotStartPage() {
  const search = useSearch({ strict: false }) as Record<string, unknown>
  const tk = useTenantKey()
  const qc = useQueryClient()
  const { entity: woE } = useMesEntity('work_order')
  const { entity: lotE } = useMesEntity('lot')
  const [step, setStep] = useState(search.wo ? 2 : 1)
  const [woId, setWoId] = useState<string | null>((search.wo as string) ?? null)
  const [plan, setPlan] = useState<StartPlan | null>(null)
  const [lots, setLots] = useState<LotDraft[]>([])
  const [lotSize, setLotSize] = useState('')
  const [qty, setQty] = useState('')
  const [created, setCreated] = useState<MesRow[] | null>(null)
  // 开批接口 422 定位到批次行的字段错误（行下标从 0 开始）
  const [lotErrs, setLotErrs] = useState<LotFieldErrors>({})

  const wos = useQuery({
    queryKey: ['mes', 'work_order', 'startable', tk],
    queryFn: async () => {
      const [a, b] = await Promise.all(
        ['released', 'in_progress'].map((s) =>
          mesApi.list('work_order', {
            wo_status: s,
            page_size: 100,
            sort_by: 'code',
          })
        )
      )
      return [...a.data, ...b.data]
    },
  })
  const wo = wos.data?.find((w) => w.id === woId) ?? null
  // 工单列表关键字（工单号 / 产品 / 流程 / 客户），最多显示 WO_SHOW 条
  const [woQ, setWoQ] = useState('')
  const woMatch = (wos.data ?? []).filter((w) =>
    [w.code, w.customer, w.order_ref, w.product_label, w.route_label]
      .map((x) => String(x ?? '').toLowerCase())
      .some((x) => x.includes(woQ.trim().toLowerCase()))
  )
  const site = useQuery({
    queryKey: ['mes', 'site', 'one', tk, plan?.site_id],
    queryFn: () => mesApi.get('site', plan!.site_id!),
    enabled: !!plan?.site_id,
  })
  const firstStep = useQuery({
    queryKey: ['mes', 'route_step', 'one', tk, plan?.first_step_id],
    queryFn: () => mesApi.get('route_step', plan!.first_step_id!),
    enabled: !!plan?.first_step_id,
  })

  const loadPlan = useMutation({
    mutationFn: (body: { id: string; lot_size?: number; qty?: number }) =>
      woApi.plan(body.id, { lot_size: body.lot_size, qty: body.qty }),
    onSuccess: (p) => {
      setPlan(p)
      setLotSize(String(p.lot_size))
      setQty(String(p.lots.reduce((s, x) => s + x.qty, 0)))
      setLots(
        p.lots.map((x) => ({
          qty: x.qty,
          carrier_id: null,
          carrier_label: null,
          slots: range(x.qty),
          source_ref: '',
          ...emptyCustomer(),
        }))
      )
    },
    onError: (e) => toast.error(mesErrorMessage(e, woE)),
  })
  // 通过 ?wo= 打开向导时：只加载一次该工单的计划
  if (step === 2 && woId && !plan && !loadPlan.isPending && !loadPlan.isError)
    loadPlan.mutate({ id: woId })

  const start = useMutation({
    mutationFn: () =>
      woApi.start(
        woId!,
        lots.map((l) => ({
          qty: l.qty,
          carrier_id: l.carrier_id,
          slots: parseSlots(l.slots) ?? undefined,
          source_ref: l.source_ref || null,
          ...customerBody(l),
        }))
      ),
    onMutate: () => setLotErrs({}),
    onSuccess: (r) => {
      setCreated(r.data)
      qc.invalidateQueries({ queryKey: ['mes'] })
      toast.success(t('mes.start.done', { count: r.data.length }))
    },
    onError: (e) => {
      const fe = startFieldErrors(e)
      if (fe) {
        // 标到对应批次行的字段下，并带回「拆分批次」这一步改正
        setLotErrs(fe)
        setStep(2)
        return
      }
      toast.error(mesErrorMessage(e, lotE ?? woE))
    },
  })

  const total = lots.reduce((s, l) => s + (Number(l.qty) || 0), 0)
  const errors = useMemo(() => {
    if (!plan) return []
    const out: string[] = []
    if (!lots.length) out.push(t('mes.start.errNoLots'))
    if (total > plan.remaining)
      out.push(t('mes.start.errOver', { total, max: plan.remaining }))
    lots.forEach((l, i) => {
      if (!(l.qty >= 1 && l.qty <= plan.max_lot_size))
        out.push(t('mes.start.errQty', { n: i + 1, max: plan.max_lot_size }))
      const sl = parseSlots(l.slots)
      if (!sl || sl.length !== l.qty || new Set(sl).size !== sl.length)
        out.push(t('mes.start.errSlots', { n: i + 1, qty: l.qty }))
    })
    const cs = lots.map((l) => l.carrier_id).filter(Boolean)
    if (new Set(cs).size !== cs.length) out.push(t('mes.start.errCarrierTwice'))
    out.push(...customerErrors(lots))
    return out
  }, [plan, lots, total])
  const set = (i: number, patch: Partial<LotDraft>) => {
    setLots((ls) => ls.map((l, k) => (k === i ? { ...l, ...patch } : l)))
    // 改过的字段清掉对应的后端错误（改归属时客户字段一起清）
    setLotErrs((all) => {
      const row = all[i]
      if (!row) return all
      const keys = Object.keys(patch).flatMap((k) =>
        k === 'ownership'
          ? ['ownership', 'customer_id', 'customer_lot_no']
          : k === 'customer_label'
            ? []
            : [k]
      )
      const next = { ...row }
      for (const k of keys) delete next[k]
      return { ...all, [i]: next }
    })
  }
  const errOf = (i: number, f: string) => lotErrs[i]?.[f]
  const hasLotErrs = Object.values(lotErrs).some((r) => Object.keys(r).length)

  const summary = wo && woE && (
    <Card>
      <CardContent className='grid gap-x-6 gap-y-1 pt-4 text-sm sm:grid-cols-3'>
        {(['code', 'product', 'route', 'lot_type', 'priority'] as const).map(
          (k) => (
            <div key={k} className='flex gap-2'>
              <span className='text-muted-foreground'>
                {t(`mes.field.work_order.${k}`)}
              </span>
              {cellValue(woE, wo, k)}
            </div>
          )
        )}
        <div className='flex items-center gap-2'>
          <span className='text-muted-foreground'>
            {t('mes.field.work_order.started_qty')}
          </span>
          <WoProgress row={wo} />
        </div>
        {plan && (
          <div className='flex gap-2 sm:col-span-3'>
            <span className='text-muted-foreground'>
              {t('mes.start.limit')}
            </span>
            {t('mes.start.limitText', {
              max: plan.max_qty,
              pct: Number(wo.over_start_limit_pct ?? 0),
              remaining: plan.remaining,
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )

  return (
    <Page title={t('menu.mes-lot-start')} description={t('mes.start.desc')}>
      <div className='space-y-4'>
        <Steps step={created ? 4 : step} />
        {step === 1 && (
          <Card>
            <CardHeader>
              <CardTitle className='text-base'>
                {t('mes.start.chooseWo')}
              </CardTitle>
            </CardHeader>
            <CardContent className='space-y-2'>
              <div className='flex items-center gap-3'>
                <Input
                  className='max-w-sm'
                  value={woQ}
                  onChange={(e) => setWoQ(e.target.value)}
                  placeholder={t('mes.start.searchWo')}
                  data-testid='wo-search'
                />
                {!!wos.data?.length && (
                  <span className='text-sm text-muted-foreground'>
                    {woMatch.length > WO_SHOW
                      ? t('mes.start.woMore', {
                          n: woMatch.length,
                          show: WO_SHOW,
                        })
                      : t('common.total', { count: woMatch.length })}
                  </span>
                )}
              </div>
              {wos.isLoading && <Loader2 className='animate-spin' />}
              {wos.data?.length === 0 && (
                <p className='text-sm text-muted-foreground'>
                  {t('mes.start.noWo')}
                </p>
              )}
              {woE &&
                woMatch.slice(0, WO_SHOW).map((w) => (
                  <button
                    key={w.id}
                    type='button'
                    data-testid={`wo-${w.code}`}
                    onClick={() => setWoId(w.id)}
                    className={cn(
                      'grid w-full items-center gap-2 rounded-md border p-3 text-start text-sm sm:grid-cols-[1fr_1fr_1fr_auto_10rem]',
                      woId === w.id && 'border-primary ring-2 ring-primary/40'
                    )}
                  >
                    <span className='truncate font-medium' title={w.code}>
                      {w.code}
                    </span>
                    <TruncCell>{cellValue(woE, w, 'product')}</TruncCell>
                    <TruncCell>{cellValue(woE, w, 'route')}</TruncCell>
                    {cellValue(woE, w, 'wo_status')}
                    <WoProgress row={w} />
                  </button>
                ))}
              <div className='flex justify-end'>
                <Button
                  disabled={!woId}
                  onClick={() => {
                    setPlan(null)
                    setStep(2)
                    loadPlan.mutate({ id: woId! })
                  }}
                >
                  {t('mes.start.next')}
                  <ArrowRight />
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
        {step >= 2 && summary}
        {step === 2 && (
          <Card>
            <CardHeader>
              <CardTitle className='text-base'>
                {t('mes.start.split')}
              </CardTitle>
            </CardHeader>
            <CardContent className='space-y-3'>
              {!plan ? (
                <Loader2 className='animate-spin' />
              ) : (
                <>
                  <div className='flex flex-wrap items-end gap-3'>
                    <div className='space-y-1'>
                      <Label htmlFor='lot-size'>
                        {t('mes.start.lotSize', { max: plan.max_lot_size })}
                      </Label>
                      <Input
                        id='lot-size'
                        type='number'
                        className='w-32'
                        value={lotSize}
                        onChange={(e) => setLotSize(e.target.value)}
                      />
                    </div>
                    <div className='space-y-1'>
                      <Label htmlFor='qty'>
                        {t('mes.start.qty', { max: plan.remaining })}
                      </Label>
                      <Input
                        id='qty'
                        type='number'
                        className='w-32'
                        value={qty}
                        onChange={(e) => setQty(e.target.value)}
                      />
                    </div>
                    <Button
                      variant='outline'
                      onClick={() =>
                        loadPlan.mutate({
                          id: woId!,
                          lot_size: Number(lotSize) || undefined,
                          qty: qty === '' ? undefined : Number(qty),
                        })
                      }
                    >
                      <RefreshCw />
                      {t('mes.start.resplit')}
                    </Button>
                  </div>
                  <div className='overflow-x-auto rounded-md border'>
                    <table className='w-full text-sm'>
                      <thead className='bg-muted/50 text-start'>
                        <tr>
                          <th className='p-2 text-start'>#</th>
                          <th className='p-2 text-start'>
                            {t('mes.start.lotNo')}
                          </th>
                          <th className='p-2 text-start'>
                            {t('mes.field.lot.qty')}
                          </th>
                          <th className='p-2 text-start'>
                            {t('mes.field.lot.carrier')}
                          </th>
                          <th className='p-2 text-start'>
                            {t('mes.start.slots')}
                          </th>
                          <th className='p-2 text-start'>
                            {t('mes.field.lot.source_ref')}
                          </th>
                          <th className='p-2 text-start'>
                            {t('mes.cust.title')}
                          </th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {lots.map((l, i) => (
                          <tr key={i} className='border-t'>
                            <td className='p-2'>{i + 1}</td>
                            <td className='p-2 font-mono text-xs text-muted-foreground'>
                              {plan.lots[i]?.lot_no ?? t('mes.start.autoNo')}
                            </td>
                            <td className='p-2'>
                              <Input
                                type='number'
                                aria-label={t('mes.field.lot.qty')}
                                className='w-20'
                                value={l.qty}
                                onChange={(e) =>
                                  set(i, {
                                    qty: Number(e.target.value),
                                    slots: range(Number(e.target.value)),
                                  })
                                }
                              />
                              <FieldMsg msg={errOf(i, 'qty')} />
                            </td>
                            <td className='w-56 p-2'>
                              <RefSelect
                                target='carrier'
                                value={l.carrier_id}
                                label={l.carrier_label}
                                filters={{ status_code: 'available' }}
                                onChange={(id, label) =>
                                  set(i, {
                                    carrier_id: id,
                                    carrier_label: label,
                                  })
                                }
                              />
                              <FieldMsg msg={errOf(i, 'carrier_id')} />
                            </td>
                            <td className='p-2'>
                              <Input
                                aria-label={t('mes.start.slots')}
                                className='w-28'
                                value={l.slots}
                                onChange={(e) =>
                                  set(i, { slots: e.target.value })
                                }
                              />
                              <FieldMsg msg={errOf(i, 'slots')} />
                            </td>
                            <td className='p-2'>
                              <Input
                                aria-label={t('mes.field.lot.source_ref')}
                                className='w-36'
                                value={l.source_ref}
                                onChange={(e) =>
                                  set(i, { source_ref: e.target.value })
                                }
                              />
                              <FieldMsg
                                msg={
                                  errOf(i, 'source_ref') ??
                                  errOf(i, 'wafer_sources')
                                }
                              />
                            </td>
                            <td className='p-2' data-testid={`lot-cust-${i}`}>
                              <CustomerFields
                                value={l}
                                onChange={(patch) => set(i, patch)}
                                errors={lotErrs[i]}
                              />
                            </td>
                            <td className='p-2'>
                              <IconButton
                                label={t('common.delete')}
                                variant='ghost'
                                onClick={() =>
                                  setLots((ls) => ls.filter((_, k) => k !== i))
                                }
                              >
                                <Trash2 className='size-4 text-destructive' />
                              </IconButton>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className='flex flex-wrap items-center gap-3 text-sm'>
                    <Button
                      variant='outline'
                      size='sm'
                      onClick={() =>
                        setLots((ls) => [
                          ...ls,
                          {
                            qty: 1,
                            carrier_id: null,
                            carrier_label: null,
                            slots: '1',
                            source_ref: '',
                            ...emptyCustomer(),
                          },
                        ])
                      }
                    >
                      <Plus />
                      {t('mes.start.addLot')}
                    </Button>
                    <span>
                      {t('mes.start.total', { total, max: plan.remaining })}
                    </span>
                  </div>
                  {hasLotErrs && (
                    <p
                      className='text-sm text-destructive'
                      role='alert'
                      data-testid='start-server-errors'
                    >
                      {t('mes.start.fe.banner')}
                    </p>
                  )}
                  {errors.length > 0 && (
                    <ul
                      className='list-disc ps-5 text-sm text-destructive'
                      role='alert'
                    >
                      {errors.map((x) => (
                        <li key={x}>{x}</li>
                      ))}
                    </ul>
                  )}
                  <div className='flex justify-between'>
                    <Button variant='outline' onClick={() => setStep(1)}>
                      <ArrowLeft />
                      {t('mes.start.back')}
                    </Button>
                    <Button
                      disabled={errors.length > 0}
                      onClick={() => setStep(3)}
                    >
                      {t('mes.start.next')}
                      <ArrowRight />
                    </Button>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        )}
        {step === 3 && plan && (
          <Card>
            <CardHeader>
              <CardTitle className='text-base'>
                {t('mes.start.confirm')}
              </CardTitle>
            </CardHeader>
            <CardContent className='space-y-3 text-sm'>
              <div className='flex flex-wrap gap-6'>
                <span>
                  <span className='text-muted-foreground'>
                    {t('mes.start.firstStep')}:{' '}
                  </span>
                  {firstStep.data
                    ? `${String(firstStep.data.seq)} · ${String(firstStep.data.operation_label ?? firstStep.data.sub_route_label ?? '')}`
                    : '—'}
                </span>
                <span>
                  <span className='text-muted-foreground'>
                    {t('mes.field.lot.site')}:{' '}
                  </span>
                  {site.data ? `${site.data.code} · ${site.data.name}` : '—'}
                </span>
                <span>
                  <span className='text-muted-foreground'>
                    {t('mes.field.lot.lot_status')}:{' '}
                  </span>
                  <Badge variant='outline'>
                    {t('mes.enum.lot_status.waiting')}
                  </Badge>
                </span>
              </div>
              <div className='rounded-md border'>
                <table className='w-full'>
                  <thead className='bg-muted/50'>
                    <tr>
                      <th className='p-2 text-start'>{t('mes.start.lotNo')}</th>
                      <th className='p-2 text-start'>
                        {t('mes.field.lot.qty')}
                      </th>
                      <th className='p-2 text-start'>
                        {t('mes.field.lot.carrier')}
                      </th>
                      <th className='p-2 text-start'>
                        {t('mes.start.wafers')}
                      </th>
                      <th className='p-2 text-start'>
                        {t('mes.cust.ownership')}
                      </th>
                      <th className='p-2 text-start'>{t('mes.cust.lotNo')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(created ?? lots).map((l, i) => {
                      const lot = l as Partial<MesRow> & Partial<LotDraft>
                      const no = created
                        ? String(lot.code)
                        : (plan.lots[i]?.lot_no ?? t('mes.start.autoNo'))
                      const sl = created
                        ? []
                        : (parseSlots(String(lot.slots)) ?? [])
                      return (
                        <tr key={i} className='border-t'>
                          <td className='p-2 font-mono'>
                            {created ? (
                              <Link
                                to='/$'
                                params={{ _splat: 'mes/lot' }}
                                search={{ q: no } as never}
                                className='text-primary underline'
                              >
                                {no}
                              </Link>
                            ) : (
                              no
                            )}
                          </td>
                          <td className='p-2'>{String(lot.qty)}</td>
                          <td className='p-2'>
                            {String(
                              (created
                                ? lot.carrier_label
                                : lot.carrier_label) ?? '—'
                            )}
                          </td>
                          <td className='p-2 font-mono text-xs text-muted-foreground'>
                            {created
                              ? `${no}.…`
                              : sl.length
                                ? `${no}.${String(sl[0]).padStart(2, '0')} … ${no}.${String(sl[sl.length - 1]).padStart(2, '0')}`
                                : '—'}
                          </td>
                          <td className='p-2'>
                            {ownershipText({
                              ownership: lot.ownership,
                              customer_label: lot.customer_label,
                            })}
                          </td>
                          <td className='p-2 font-mono'>
                            {String(lot.customer_lot_no || '—')}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              {!created && (
                <p className='text-xs text-muted-foreground'>
                  {t('mes.start.previewNote')}
                </p>
              )}
              <div className='flex justify-between'>
                {created ? (
                  <Button
                    variant='outline'
                    onClick={() => {
                      setCreated(null)
                      setPlan(null)
                      setStep(1)
                    }}
                  >
                    {t('mes.start.again')}
                  </Button>
                ) : (
                  <Button variant='outline' onClick={() => setStep(2)}>
                    <ArrowLeft />
                    {t('mes.start.back')}
                  </Button>
                )}
                {!created && (
                  <Button
                    onClick={() => start.mutate()}
                    disabled={start.isPending}
                  >
                    {start.isPending ? (
                      <Loader2 className='animate-spin' />
                    ) : (
                      <Check />
                    )}
                    {t('mes.start.confirmStart', { count: lots.length, total })}
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </Page>
  )
}

/** 保持单行的网格单元格；完整文本显示在提示中。 */
function TruncCell({ children }: { children: React.ReactNode }) {
  return (
    <span
      className='min-w-0 truncate'
      ref={(el) => {
        if (el) el.title = el.textContent ?? ''
      }}
    >
      {children}
    </span>
  )
}
