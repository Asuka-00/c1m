/**
 * 按 bin 拆批对话框（F7 / B8）：先预览再提交。
 *
 * - 有坐标图的晶圆各 bin 数量取自图（只读）；没有坐标图时逐 bin 人工录入并选原因码。
 * - 预览显示 bin 分档汇总表（每片各 bin 数量、合计、排除标记）和每片守恒结果（通过 / 不通过、差额）；
 *   守恒不通过或预览报错时提交按钮不可用。
 * - 默认每个 bin 一个子批，提交后列出子批及其 bin_code。撤销推到 P2（BIN-12 / D41）。
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Plus, Trash2, TriangleAlert } from 'lucide-react'
import { toast } from 'sonner'
import {
  execApi,
  type BinSplitPreview,
  type ExecContext,
  type TransformResult,
} from '@/lib/api/mes/execution'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { IconButton } from '@/components/icon-button'
import { RefSelect } from '@/features/mes/common/ref-select'
import {
  binDraftErrors,
  binSplitBody,
  binSplitErrorText,
  binSummary,
  emptyBinDraft,
  manualSum,
  type BinDraft,
  type BinRow,
} from './bin-split-plan'
import { trfWarningText } from './transform-plan'
import { useWaferMaps } from './wafer-maps'

export function BinSplitDialog({
  cx,
  open,
  onOpenChange,
  initial,
}: {
  cx: ExecContext
  open: boolean
  onOpenChange: (v: boolean) => void
  /** 初始草稿（测试用） */
  initial?: Partial<BinDraft>
}) {
  const qc = useQueryClient()
  const [d, setD] = useState<BinDraft>(() => ({
    ...emptyBinDraft(),
    ...initial,
  }))
  const [preview, setPreview] = useState<{
    key: string
    data: BinSplitPreview
  } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [done, setDone] = useState<TransformResult | null>(null)
  const wafers = useWaferMaps(cx, open)
  const body = binSplitBody(String(cx.lot.id), wafers, d)
  const key = JSON.stringify(body)
  const errors = binDraftErrors(wafers, d)
  const fresh = preview?.key === key ? preview.data : null
  const summary = fresh ? binSummary(fresh) : null

  const edit = (patch: Partial<BinDraft>) => {
    setD((x) => ({ ...x, ...patch }))
    setErr(null)
  }
  const setRows = (wid: string, rows: BinRow[]) =>
    edit({ manual: { ...d.manual, [wid]: rows } })

  const pv = useMutation({
    mutationFn: () => execApi.binSplitPreview(body),
    onSuccess: (data) => {
      setPreview({ key, data })
      setErr(null)
    },
    onError: (e) => {
      setPreview(null)
      setErr(binSplitErrorText(e))
    },
  })
  const commit = useMutation({
    mutationFn: () => execApi.binSplit(body),
    onSuccess: (r) => {
      setDone(r)
      toast.success(
        t('mes.bin.done', {
          list: r.children
            .map((c) => `${String(c.code)}（${String(c.bin_code ?? '')}）`)
            .join('、'),
        })
      )
      for (const w of r.warnings ?? []) toast.warning(trfWarningText(w))
      qc.invalidateQueries({ queryKey: ['mes'] })
    },
    onError: (e) => {
      const m = binSplitErrorText(e)
      setErr(m)
      toast.error(m)
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>
            {t('mes.bin.title')} · {String(cx.lot.code)}
          </DialogTitle>
          <DialogDescription>{t('mes.bin.desc')}</DialogDescription>
        </DialogHeader>
        {done ? (
          <table className='w-full text-sm' data-testid='bin-done'>
            <thead className='text-muted-foreground'>
              <tr>
                <th className='p-1 text-start'>{t('mes.bin.child')}</th>
                <th className='p-1 text-start'>{t('mes.bin.bin')}</th>
                <th className='p-1 text-end'>{t('mes.bin.qty')}</th>
              </tr>
            </thead>
            <tbody>
              {done.children.map((c) => (
                <tr key={String(c.id)} className='border-t'>
                  <td className='p-1'>{String(c.code)}</td>
                  <td className='p-1' data-testid='bin-child-code'>
                    {String(c.bin_code ?? '')}
                  </td>
                  <td className='p-1 text-end'>{String(c.qty ?? '')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <>
            <div className='grid gap-2 text-sm'>
              {wafers.map((w) => {
                const rows = d.manual[w.id] ?? []
                return (
                  <div
                    key={w.id}
                    className='grid gap-1 rounded-md border p-2'
                    data-testid='bin-wafer'
                  >
                    <div className='flex items-center justify-between'>
                      <span className='font-medium'>{w.code}</span>
                      <span className='text-muted-foreground'>
                        {w.map
                          ? t('mes.trf.src.map', { v: w.map.map_version })
                          : w.map === null
                            ? t('mes.bin.noMap', { sum: manualSum(rows) })
                            : t('mes.trf.src.unknown')}
                      </span>
                    </div>
                    {w.map === null && (
                      <div className='grid gap-1'>
                        {rows.map((r, k) => (
                          <div key={k} className='flex items-center gap-2'>
                            <Input
                              className='h-8 w-24'
                              aria-label={t('mes.bin.binOf', {
                                wafer: w.code,
                                n: k + 1,
                              })}
                              value={r.bin}
                              onChange={(e) =>
                                setRows(
                                  w.id,
                                  rows.map((x, i) =>
                                    i === k ? { ...x, bin: e.target.value } : x
                                  )
                                )
                              }
                            />
                            <Input
                              className='h-8 w-24'
                              inputMode='numeric'
                              aria-label={t('mes.bin.qtyOf', {
                                wafer: w.code,
                                n: k + 1,
                              })}
                              value={r.qty}
                              onChange={(e) =>
                                setRows(
                                  w.id,
                                  rows.map((x, i) =>
                                    i === k ? { ...x, qty: e.target.value } : x
                                  )
                                )
                              }
                            />
                            <IconButton
                              label={t('common.delete')}
                              variant='ghost'
                              onClick={() =>
                                setRows(
                                  w.id,
                                  rows.filter((_, i) => i !== k)
                                )
                              }
                            >
                              <Trash2 className='size-4' />
                            </IconButton>
                          </div>
                        ))}
                        <Button
                          size='sm'
                          variant='outline'
                          className='justify-self-start'
                          onClick={() =>
                            setRows(w.id, [...rows, { bin: '', qty: '' }])
                          }
                        >
                          <Plus className='size-4' />
                          {t('mes.bin.addBin')}
                        </Button>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
            <div className='grid gap-1'>
              <Label>
                {t('mes.exec.reason')}
                {wafers.some((w) => w.map === null) && (
                  <span className='text-destructive'> *</span>
                )}
              </Label>
              <RefSelect
                target='reason_code'
                value={d.reason_id}
                label={d.reason_label}
                onChange={(id, label) =>
                  edit({ reason_id: id, reason_label: label })
                }
              />
            </div>
            <div className='grid gap-1'>
              <Label htmlFor='bin-comment'>{t('mes.exec.comment')}</Label>
              <Textarea
                id='bin-comment'
                rows={2}
                maxLength={300}
                value={d.comment}
                onChange={(e) => edit({ comment: e.target.value })}
              />
            </div>
            {errors.length > 0 && (
              <ul
                className='list-disc ps-5 text-sm text-destructive'
                data-testid='bin-local-errors'
              >
                {errors.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            )}
            {err && (
              <Alert variant='destructive' data-testid='bin-error'>
                <TriangleAlert />
                <AlertDescription>{err}</AlertDescription>
              </Alert>
            )}
            {fresh && summary && <BinSummary p={fresh} s={summary} />}
            {preview && !fresh && (
              <div
                className='text-sm text-muted-foreground'
                data-testid='bin-stale'
              >
                {t('mes.trf.stale')}
              </div>
            )}
          </>
        )}
        <DialogFooter>
          {done ? (
            <Button onClick={() => onOpenChange(false)}>
              {t('common.close')}
            </Button>
          ) : (
            <>
              <Button
                variant='outline'
                data-testid='bin-preview'
                disabled={errors.length > 0 || pv.isPending}
                onClick={() => pv.mutate()}
              >
                {t('mes.trf.preview')}
              </Button>
              <Button
                data-testid='bin-commit'
                disabled={!summary?.ok || errors.length > 0 || commit.isPending}
                onClick={() => commit.mutate()}
              >
                {t('mes.bin.commit')}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** 预览：bin 分档汇总表、每片守恒、将生成的子批。 */
function BinSummary({
  p,
  s,
}: {
  p: BinSplitPreview
  s: ReturnType<typeof binSummary>
}) {
  return (
    <div className='grid gap-2 text-sm' data-testid='bin-preview-result'>
      <div className='font-medium'>{t('mes.bin.summary')}</div>
      <table className='w-full' data-testid='bin-summary'>
        <thead className='text-muted-foreground'>
          <tr>
            <th className='p-1 text-start'>{t('mes.bin.bin')}</th>
            {p.inputs.map((x) => (
              <th key={x.wafer_id} className='p-1 text-end'>
                {x.wafer}
              </th>
            ))}
            <th className='p-1 text-end'>{t('mes.trf.total')}</th>
          </tr>
        </thead>
        <tbody>
          {s.bins.map((b) => (
            <tr key={b.bin} className='border-t' data-testid='bin-row'>
              <td className='p-1'>
                {b.bin}
                {b.excluded && (
                  <Badge variant='secondary' className='ms-2'>
                    {t('mes.bin.excluded')}
                  </Badge>
                )}
              </td>
              {b.per.map((n, i) => (
                <td key={i} className='p-1 text-end'>
                  {n}
                </td>
              ))}
              <td className='p-1 text-end'>{b.total}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className='grid gap-1'>
        {s.wafers.map((w) => (
          <li
            key={w.wafer}
            data-testid='bin-conserve'
            className={w.ok ? '' : 'text-destructive'}
          >
            <Badge
              variant={w.ok ? 'secondary' : 'destructive'}
              className='me-2'
            >
              {w.ok ? t('mes.bin.ok') : t('mes.bin.fail')}
            </Badge>
            {t('mes.bin.conserve', {
              wafer: w.wafer,
              children: w.children,
              excluded: w.excluded,
              total: w.total,
            })}
            {!w.ok &&
              ` · ${t('mes.bin.diff', { diff: w.diff > 0 ? `+${w.diff}` : w.diff })}`}
          </li>
        ))}
      </ul>
      <div className='font-medium'>{t('mes.bin.children')}</div>
      <ul className='list-disc ps-5'>
        {p.outputs.map((o) => (
          <li key={o.bin_code} data-testid='bin-output'>
            {t('mes.bin.outLine', { bin: o.bin_code, qty: o.qty })}
          </li>
        ))}
      </ul>
      {p.warnings.map((w, i) => (
        <Alert key={i}>
          <TriangleAlert />
          <AlertDescription>{trfWarningText(w)}</AlertDescription>
        </Alert>
      ))}
    </div>
  )
}
