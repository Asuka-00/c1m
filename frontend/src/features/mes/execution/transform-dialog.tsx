/**
 * 单位转换对话框（F8 / D41）：先预览再提交。
 *
 * - 有坐标图的晶圆只读显示良品数；没有坐标图时可人工录入良品 / 不良数，录入后必须选原因码；
 *   都不录则由后端用产品 gross die（预览提示 no_map_gross_die）。
 * - 每个输出（产品、流程、追踪单位）按晶圆分配 die；单输出时默认分配全部良品。
 * - 改动任何输入后预览失效，需要重新预览才能提交。撤销转换推到 P2（D41），提交前以预览把关。
 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Plus, Trash2, TriangleAlert } from 'lucide-react'
import { toast } from 'sonner'
import {
  execApi,
  type ExecContext,
  type TransformPreview,
  type TransformResult,
} from '@/lib/api/mes/execution'
import { Alert, AlertDescription } from '@/components/ui/alert'
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
import { Pick } from './exec-parts'
import {
  TRACK_UNIT_KINDS,
  TRANSFORM_TYPES,
  balance,
  draftErrors,
  emptyDraft,
  emptyOutput,
  transformBody,
  transformErrorText,
  trfWarningText,
  type TrfDraft,
  type TrfOutput,
} from './transform-plan'
import { useWaferMaps } from './wafer-maps'

export function TransformDialog({
  cx,
  open,
  onOpenChange,
  initial,
}: {
  cx: ExecContext
  open: boolean
  onOpenChange: (v: boolean) => void
  /** 初始草稿（测试用） */
  initial?: Partial<TrfDraft>
}) {
  const qc = useQueryClient()
  const [d, setD] = useState<TrfDraft>(() => ({ ...emptyDraft(), ...initial }))
  const [preview, setPreview] = useState<{
    key: string
    data: TransformPreview
  } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [done, setDone] = useState<TransformResult | null>(null)
  const wafers = useWaferMaps(cx, open)
  const lotId = String(cx.lot.id)
  const body = transformBody(lotId, wafers, d)
  const key = JSON.stringify(body)
  const errors = draftErrors(wafers, d)
  const fresh = preview?.key === key ? preview.data : null
  const bal = balance(wafers, d)

  const edit = (patch: Partial<TrfDraft>) => {
    setD((x) => ({ ...x, ...patch }))
    setErr(null)
  }
  const setOut = (i: number, patch: Partial<TrfOutput>) =>
    edit({
      outputs: d.outputs.map((o, k) => (k === i ? { ...o, ...patch } : o)),
    })

  const pv = useMutation({
    mutationFn: () => execApi.transformPreview(body),
    onSuccess: (data) => {
      setPreview({ key, data })
      setErr(null)
    },
    onError: (e) => {
      setPreview(null)
      setErr(transformErrorText(e))
    },
  })
  const commit = useMutation({
    mutationFn: () => execApi.transform(body),
    onSuccess: (r) => {
      setDone(r)
      toast.success(
        t('mes.trf.done', {
          list: r.children.map((c) => String(c.code)).join('、'),
        })
      )
      for (const w of r.warnings ?? []) toast.warning(trfWarningText(w))
      qc.invalidateQueries({ queryKey: ['mes'] })
    },
    onError: (e) => {
      const m = transformErrorText(e)
      setErr(m)
      toast.error(m)
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>
            {t('mes.trf.title')} · {String(cx.lot.code)}
          </DialogTitle>
          <DialogDescription>{t('mes.trf.desc')}</DialogDescription>
        </DialogHeader>
        {done ? (
          <div className='grid gap-2 text-sm' data-testid='trf-done'>
            <div>{t('mes.trf.children')}</div>
            <ul className='list-disc ps-5'>
              {done.children.map((c) => (
                <li key={String(c.id)}>
                  {String(c.code)} · {String(c.qty ?? '')}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <>
            <Pick
              id='trf-type'
              label={t('mes.trf.type')}
              required
              none={false}
              value={d.type}
              onChange={(v) => edit({ type: v as TrfDraft['type'] })}
              options={TRANSFORM_TYPES.map((x) => ({
                id: x,
                label: t(`mes.trf.types.${x}`),
              }))}
            />
            <div className='grid gap-1'>
              <Label>{t('mes.trf.wafers')}</Label>
              <table className='w-full text-sm' data-testid='trf-wafers'>
                <thead className='text-muted-foreground'>
                  <tr className='text-start'>
                    <th className='p-1 text-start'>{t('mes.trf.wafer')}</th>
                    <th className='p-1 text-start'>{t('mes.trf.source')}</th>
                    <th className='p-1 text-start'>{t('mes.trf.good')}</th>
                    <th className='p-1 text-start'>{t('mes.trf.fail')}</th>
                    <th className='p-1 text-start'>{t('mes.trf.allocated')}</th>
                  </tr>
                </thead>
                <tbody>
                  {wafers.map((w, i) => {
                    const m = d.manual[w.id] ?? { good: '', fail: '' }
                    const setM = (p: Partial<typeof m>) =>
                      edit({ manual: { ...d.manual, [w.id]: { ...m, ...p } } })
                    const b = bal[i]
                    return (
                      <tr
                        key={w.id}
                        className='border-t'
                        data-testid='trf-wafer'
                      >
                        <td className='p-1'>{w.code}</td>
                        <td className='p-1'>
                          {w.map
                            ? t('mes.trf.src.map', { v: w.map.map_version })
                            : w.map === null
                              ? t('mes.trf.src.noMap')
                              : t('mes.trf.src.unknown')}
                        </td>
                        <td className='p-1'>
                          {w.map ? (
                            <span data-testid='trf-map-good'>
                              {w.map.good_qty}
                            </span>
                          ) : w.map === null ? (
                            <Input
                              className='h-8 w-24'
                              inputMode='numeric'
                              aria-label={`${w.code} ${t('mes.trf.good')}`}
                              placeholder={t('mes.trf.grossHint')}
                              value={m.good}
                              onChange={(e) => setM({ good: e.target.value })}
                            />
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className='p-1'>
                          {w.map ? (
                            w.map.total_qty -
                            w.map.good_qty -
                            w.map.excluded_qty
                          ) : w.map === null ? (
                            <Input
                              className='h-8 w-20'
                              inputMode='numeric'
                              aria-label={`${w.code} ${t('mes.trf.fail')}`}
                              value={m.fail}
                              onChange={(e) => setM({ fail: e.target.value })}
                            />
                          ) : (
                            '—'
                          )}
                        </td>
                        <td
                          className={b.diff ? 'p-1 text-destructive' : 'p-1'}
                          data-testid='trf-balance'
                        >
                          {b.allocated}
                          {b.diff ? ` (${b.diff > 0 ? '+' : ''}${b.diff})` : ''}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <div className='grid gap-3'>
              {d.outputs.map((o, i) => (
                <div
                  key={i}
                  className='grid gap-2 rounded-md border p-2'
                  data-testid='trf-output'
                >
                  <div className='flex items-center justify-between text-sm font-medium'>
                    {t('mes.trf.output', { n: i + 1 })}
                    {d.outputs.length > 1 && (
                      <IconButton
                        label={t('common.delete')}
                        variant='ghost'
                        onClick={() =>
                          edit({ outputs: d.outputs.filter((_, k) => k !== i) })
                        }
                      >
                        <Trash2 className='size-4' />
                      </IconButton>
                    )}
                  </div>
                  <div className='grid gap-2 sm:grid-cols-2'>
                    <div className='grid gap-1'>
                      <Label>{t('mes.trf.product')} *</Label>
                      <RefSelect
                        target='product'
                        value={o.product_id}
                        label={o.product_label}
                        onChange={(id, label) =>
                          setOut(i, { product_id: id, product_label: label })
                        }
                      />
                    </div>
                    <div className='grid gap-1'>
                      <Label>{t('mes.trf.route')} *</Label>
                      <RefSelect
                        target='route'
                        value={o.route_id}
                        label={o.route_label}
                        onChange={(id, label) =>
                          setOut(i, { route_id: id, route_label: label })
                        }
                      />
                    </div>
                    <Pick
                      id={`trf-kind-${i}`}
                      label={t('mes.trf.kind')}
                      required
                      none={false}
                      value={o.kind}
                      onChange={(v) =>
                        setOut(i, { kind: v as TrfOutput['kind'] })
                      }
                      options={TRACK_UNIT_KINDS.map((k) => ({
                        id: k,
                        label: t(`mes.trf.kinds.${k}`),
                      }))}
                    />
                    {o.kind === 'strip' && (
                      <div className='grid gap-1'>
                        <Label htmlFor={`trf-qty-${i}`}>
                          {t('mes.trf.stripQty')} *
                        </Label>
                        <Input
                          id={`trf-qty-${i}`}
                          inputMode='numeric'
                          value={o.qty}
                          onChange={(e) => setOut(i, { qty: e.target.value })}
                        />
                      </div>
                    )}
                  </div>
                  <div className='flex flex-wrap gap-2'>
                    {wafers.map((w) => (
                      <Label
                        key={w.id}
                        className='flex items-center gap-1 font-normal'
                      >
                        {w.code}
                        <Input
                          className='h-8 w-20'
                          inputMode='numeric'
                          aria-label={t('mes.trf.allocOf', {
                            n: i + 1,
                            wafer: w.code,
                          })}
                          placeholder={
                            d.outputs.length === 1 ? t('mes.trf.allGood') : '0'
                          }
                          value={o.alloc[w.id] ?? ''}
                          onChange={(e) =>
                            setOut(i, {
                              alloc: { ...o.alloc, [w.id]: e.target.value },
                            })
                          }
                        />
                      </Label>
                    ))}
                  </div>
                </div>
              ))}
              <Button
                size='sm'
                variant='outline'
                className='justify-self-start'
                onClick={() => edit({ outputs: [...d.outputs, emptyOutput()] })}
              >
                <Plus className='size-4' />
                {t('mes.trf.addOutput')}
              </Button>
            </div>
            <div className='grid gap-1'>
              <Label>
                {t('mes.exec.reason')}
                {wafers.some((w) => w.map === null && d.manual[w.id]?.good) && (
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
              <Label htmlFor='trf-comment'>{t('mes.exec.comment')}</Label>
              <Textarea
                id='trf-comment'
                rows={2}
                maxLength={300}
                value={d.comment}
                onChange={(e) => edit({ comment: e.target.value })}
              />
            </div>
            {errors.length > 0 && (
              <ul
                className='list-disc ps-5 text-sm text-destructive'
                data-testid='trf-local-errors'
              >
                {errors.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            )}
            {err && (
              <Alert variant='destructive' data-testid='trf-error'>
                <TriangleAlert />
                <AlertDescription>{err}</AlertDescription>
              </Alert>
            )}
            {fresh && <PreviewTable p={fresh} />}
            {preview && !fresh && (
              <div
                className='text-sm text-muted-foreground'
                data-testid='trf-stale'
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
                data-testid='trf-preview'
                disabled={errors.length > 0 || pv.isPending}
                onClick={() => pv.mutate()}
              >
                {t('mes.trf.preview')}
              </Button>
              <Button
                data-testid='trf-commit'
                disabled={!fresh || errors.length > 0 || commit.isPending}
                onClick={() => commit.mutate()}
              >
                {t('mes.trf.commit')}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

const SRC_KEY = {
  map: 'mes.trf.src.mapShort',
  manual: 'mes.trf.src.manual',
  gross_die: 'mes.trf.src.gross',
} as const

/** 预览结果：逐片晶圆良品来源与数量、输出数量、提示。 */
function PreviewTable({ p }: { p: TransformPreview }) {
  return (
    <div className='grid gap-2 text-sm' data-testid='trf-preview-result'>
      <div className='font-medium'>{t('mes.trf.previewTitle')}</div>
      <table className='w-full'>
        <thead className='text-muted-foreground'>
          <tr>
            <th className='p-1 text-start'>{t('mes.trf.wafer')}</th>
            <th className='p-1 text-start'>{t('mes.trf.source')}</th>
            <th className='p-1 text-end'>{t('mes.trf.total')}</th>
            <th className='p-1 text-end'>{t('mes.trf.good')}</th>
            <th className='p-1 text-end'>{t('mes.trf.fail')}</th>
            <th className='p-1 text-end'>{t('mes.trf.excluded')}</th>
            <th className='p-1 text-end'>{t('mes.trf.allocated')}</th>
          </tr>
        </thead>
        <tbody>
          {p.inputs.map((x) => (
            <tr key={x.wafer_id} className='border-t'>
              <td className='p-1'>{x.wafer}</td>
              <td className='p-1'>
                {t(SRC_KEY[x.good_source] ?? x.good_source, {
                  v: x.map_version,
                })}
              </td>
              <td className='p-1 text-end'>{x.total_qty}</td>
              <td className='p-1 text-end'>{x.good_qty}</td>
              <td className='p-1 text-end'>{x.fail_qty}</td>
              <td className='p-1 text-end'>{x.excluded_qty}</td>
              <td className='p-1 text-end'>{x.allocated_qty}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className='list-disc ps-5'>
        {p.outputs.map((o, i) => (
          <li key={i}>
            {t('mes.trf.outLine', {
              n: i + 1,
              kind: t(`mes.trf.kinds.${o.track_unit_kind}`),
              qty: o.qty,
              dies: o.die_qty,
            })}
          </li>
        ))}
      </ul>
      {p.warnings.map((w, i) => (
        <Alert key={i} data-testid='trf-warning'>
          <TriangleAlert />
          <AlertDescription>{trfWarningText(w)}</AlertDescription>
        </Alert>
      ))}
    </div>
  )
}
