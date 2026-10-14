/** 打标作业页面（P3-F4）：打标预览、打印、检验、重打（填原因）、作废。 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { toast } from 'sonner'
import {
  COMMENT_MAX,
  inspectionsByPrint,
  isLocked,
  MARKING_MOCK,
  markingApi,
  markingSignature,
  reprintErrors,
  TRACE_CODE_RULE,
  traceCodeError,
  type InspectResult,
  type MarkingRecord,
} from '@/lib/api/mes/marking'
import { decimalText } from '@/lib/decimal'
import { siteToday } from '@/lib/site-tz'
import { cn } from '@/lib/utils'
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
import { rangeParam } from '@/components/crud/filter-defs'
import { useMesCan } from '@/features/mes/common/mes-perm'
import { MARKING_PERM, markingErrorMessage, useIdemKey } from './marking-rules'

const REC_KEY = ['mes', 'marking', 'records']
const dash = (v: unknown) => (v == null || v === '' ? '—' : String(v))

/** 检验状态徽标（只读 latest_inspection_status）。 */
export function InspectBadge({ status }: { status: string }) {
  const tone =
    status === 'pass'
      ? 'default'
      : status === 'fail'
        ? 'destructive'
        : 'secondary'
  return (
    <Badge variant={tone} data-testid={`insp-${status}`}>
      {t(`mes.marking.insp.${status}`)}
    </Badge>
  )
}

/** 打标作业页（菜单组件 key `mes-page:marking`）。 */
export default function MarkingJobPage() {
  const can = useMesCan()
  const qc = useQueryClient()
  const keyOf = useIdemKey()
  const [lot, setLot] = useState('')
  const [lotQ, setLotQ] = useState('')
  const [equipment, setEquipment] = useState('')
  const today = siteToday()
  const [from, setFrom] = useState(today)
  const [to, setTo] = useState(today)
  const [sel, setSel] = useState<string | null>(null)
  const preview = useQuery({
    queryKey: ['mes', 'marking', 'preview', lotQ],
    queryFn: () => markingApi.preview(lotQ),
    enabled: !!lotQ,
    retry: false,
  })
  // D77：marked_at 半开区间，_from 站点当天 0 点、_to 站点次日 0 点
  const range = {
    marked_at_from: from ? rangeParam(from, false) : undefined,
    marked_at_to: to ? rangeParam(to, true) : undefined,
  }
  const records = useQuery({
    queryKey: [...REC_KEY, range],
    queryFn: () => markingApi.records(range),
  })
  const print = useMutation({
    mutationFn: () => {
      const body = {
        lot_id: preview.data!.lot_id,
        equipment_id: equipment || null,
      }
      return markingApi.mark(body, keyOf(markingSignature('mark', body)))
    },
    onSuccess: (r) => {
      toast.success(t('mes.marking.done.print', { code: r.trace_code }))
      setSel(r.id)
      void qc.invalidateQueries({ queryKey: ['mes', 'marking'] })
    },
    onError: (e) => toast.error(markingErrorMessage(e)),
  })
  const cur = records.data?.find((r) => r.id === sel)
  const p = preview.data
  return (
    <Page
      title={t('mes.marking.jobTitle')}
      description={
        MARKING_MOCK ? t('mes.marking.mockHint') : t('mes.marking.jobDesc')
      }
    >
      <form
        className='flex flex-wrap items-end gap-3'
        onSubmit={(e) => {
          e.preventDefault()
          setLotQ(lot.trim())
        }}
      >
        <div className='grid w-56 gap-1'>
          <Label htmlFor='mk-lot'>{t('mes.marking.col.lot')}</Label>
          <Input
            id='mk-lot'
            value={lot}
            onChange={(e) => setLot(e.target.value)}
            data-testid='mk-lot'
          />
        </div>
        <Button type='submit' data-testid='mk-preview'>
          {t('mes.marking.preview')}
        </Button>
      </form>
      {preview.error && (
        <p className='text-sm text-destructive' data-testid='mk-preview-err'>
          {markingErrorMessage(preview.error)}
        </p>
      )}
      {p && (
        <div
          className='grid gap-3 rounded-md border p-4'
          data-testid='mk-preview-box'
        >
          <div className='flex flex-wrap gap-4 text-sm'>
            <span>
              {t('mes.marking.col.lot')}: <b>{p.lot}</b>
            </span>
            <span>
              {t('mes.marking.col.template')}: {p.template_code} v
              {p.template_version}
            </span>
            <span>
              {t('mes.marking.col.dateCode')}: {p.date_code}
            </span>
            <span>
              {t('mes.marking.col.qty')}: {decimalText(p.qty)}
            </span>
            {p.bin && (
              <span>
                {t('mes.marking.col.bin')}: {p.bin}
              </span>
            )}
          </div>
          <pre
            className='rounded bg-muted p-3 font-mono text-lg'
            data-testid='mk-preview-lines'
          >
            {p.lines.join('\n')}
          </pre>
          {!p.trace_code && (
            <p className='text-xs text-muted-foreground'>
              {t('mes.marking.traceAssignedHint')}
            </p>
          )}
          {can(MARKING_PERM.exec) && !p.trace_code && (
            <div className='flex flex-wrap items-end gap-3'>
              <div className='grid w-48 gap-1'>
                <Label htmlFor='mk-eqp'>{t('mes.marking.col.equipment')}</Label>
                <Input
                  id='mk-eqp'
                  value={equipment}
                  onChange={(e) => setEquipment(e.target.value)}
                />
              </div>
              <Button
                onClick={() => print.mutate()}
                disabled={print.isPending}
                data-testid='mk-print'
              >
                {t('mes.marking.print')}
              </Button>
            </div>
          )}
        </div>
      )}
      <div className='flex flex-wrap items-end gap-3'>
        <div className='grid gap-1'>
          <Label htmlFor='mk-from'>{t('mes.marking.markedFrom')}</Label>
          <Input
            id='mk-from'
            type='date'
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </div>
        <div className='grid gap-1'>
          <Label htmlFor='mk-to'>{t('mes.marking.markedTo')}</Label>
          <Input
            id='mk-to'
            type='date'
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </div>
      </div>
      <Table data-testid='mk-records'>
        <TableHeader>
          <TableRow>
            {[
              'lot',
              'traceCode',
              'template',
              'reprints',
              'inspection',
              'markedAt',
            ].map((c) => (
              <TableHead key={c}>{t(`mes.marking.col.${c}`)}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {(records.data ?? []).map((r) => (
            <TableRow
              key={r.id}
              onClick={() => setSel(r.id)}
              className={cn('cursor-pointer', r.id === sel && 'bg-muted')}
              data-testid={`mk-row-${r.lot}`}
            >
              <TableCell>{r.lot}</TableCell>
              <TableCell className='font-mono'>{r.trace_code}</TableCell>
              <TableCell>
                {r.template_code} v{r.template_version}
              </TableCell>
              <TableCell>{r.reprint_count}</TableCell>
              <TableCell>
                {r.voided ? (
                  <Badge variant='outline'>{t('mes.marking.voided')}</Badge>
                ) : (
                  <InspectBadge status={r.latest_inspection_status} />
                )}
              </TableCell>
              <TableCell>{fmtDateTime(r.marked_at)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {cur && <RecordDetail rec={cur} />}
    </Page>
  )
}

function FieldErr({ k, msg }: { k: string; msg?: string }) {
  return msg ? (
    <p className='text-sm text-destructive' data-testid={`mk-err-${k}`}>
      {msg}
    </p>
  ) : null
}

type Act = 'inspect' | 'reprint' | 'void'

/** 记录详情：内容、打印履历（seq）、按打印分组的检验履历、动作。 */
function RecordDetail({ rec }: { rec: MarkingRecord }) {
  const can = useMesCan()
  const [act, setAct] = useState<Act | null>(null)
  const locked = isLocked(rec)
  const exec = can(MARKING_PERM.exec)
  return (
    <div
      className='mt-4 grid gap-4 rounded-md border p-4'
      data-testid='mk-detail'
    >
      <div className='flex flex-wrap items-center gap-2'>
        <h3 className='font-mono font-semibold'>{rec.trace_code}</h3>
        {rec.voided ? (
          <Badge variant='outline' data-testid='mk-voided'>
            {t('mes.marking.voided')}
          </Badge>
        ) : (
          <InspectBadge status={rec.latest_inspection_status} />
        )}
        {exec && (
          <div className='ms-auto flex flex-wrap gap-2'>
            <Button
              variant='outline'
              disabled={locked || rec.latest_inspection_status !== 'pending'}
              onClick={() => setAct('inspect')}
              data-testid='mk-act-inspect'
            >
              {t('mes.marking.inspect')}
            </Button>
            <Button
              variant='outline'
              disabled={locked || rec.latest_inspection_status !== 'fail'}
              onClick={() => setAct('reprint')}
              data-testid='mk-act-reprint'
            >
              {t('mes.marking.reprint')}
            </Button>
            <Button
              variant='destructive'
              disabled={locked}
              onClick={() => setAct('void')}
              data-testid='mk-act-void'
            >
              {t('mes.marking.void')}
            </Button>
          </div>
        )}
      </div>
      {locked && (
        <p className='text-sm text-muted-foreground' data-testid='mk-locked'>
          {rec.voided
            ? t('mes.marking.voidedHint', {
                by: dash(rec.voided_by),
                comment: dash(rec.void_comment),
              })
            : t('mes.marking.scrappedHint')}
        </p>
      )}
      <pre className='rounded bg-muted p-2 font-mono text-sm'>
        {rec.content.join('\n')}
      </pre>
      <div data-testid='mk-prints'>
        <p className='mb-1 text-sm font-medium'>{t('mes.marking.printLog')}</p>
        {inspectionsByPrint(rec).map(({ print, inspections }) => (
          <div
            key={print.id}
            className='mb-2 rounded border p-2 text-sm'
            data-testid={`mk-print-${print.seq}`}
          >
            <div className='flex flex-wrap gap-3'>
              <b>#{print.seq}</b>
              <span>
                {print.seq === 1
                  ? t('mes.marking.firstPrint')
                  : t('mes.marking.reprint')}
              </span>
              <span>{fmtDateTime(print.printed_at)}</span>
              <span>{dash(print.operator)}</span>
              <span>{t(`mes.marking.source.${print.source}`)}</span>
              {print.seq > 1 && (
                <span data-testid={`mk-print-reason-${print.seq}`}>
                  {dash(print.reason_code ?? print.reason_id)} ·{' '}
                  {dash(print.comment)}
                </span>
              )}
            </div>
            {inspections.length === 0 ? (
              <p className='text-muted-foreground'>
                {t('mes.marking.insp.pending')}
              </p>
            ) : (
              inspections.map((i) => (
                <div
                  key={i.id}
                  className='mt-1 flex flex-wrap items-center gap-2'
                >
                  <InspectBadge status={i.result} />
                  <span>{fmtDateTime(i.inspected_at)}</span>
                  <span>{dash(i.inspected_by)}</span>
                  {i.read_code && i.read_code !== i.expected_code && (
                    <span data-testid='mk-ocr-diff' className='font-mono'>
                      {t('mes.marking.ocrDiff', {
                        expected: dash(i.expected_code),
                        read: i.read_code,
                      })}
                    </span>
                  )}
                  {i.comment && <span>{i.comment}</span>}
                </div>
              ))
            )}
          </div>
        ))}
      </div>
      {act && <ActDialog rec={rec} act={act} onClose={() => setAct(null)} />}
    </div>
  )
}

/** 检验 / 重打 / 作废对话框（作废需二次确认）。 */
function ActDialog({
  rec,
  act,
  onClose,
}: {
  rec: MarkingRecord
  act: Act
  onClose: () => void
}) {
  const qc = useQueryClient()
  const keyOf = useIdemKey()
  const [result, setResult] = useState<InspectResult>('pass')
  const [readCode, setReadCode] = useState('')
  const [reasonId, setReasonId] = useState('')
  const [comment, setComment] = useState('')
  const [confirm, setConfirm] = useState(false)
  const [errs, setErrs] = useState<Record<string, string>>({})
  const m = useMutation({
    mutationFn: () => {
      if (act === 'inspect') {
        const body = {
          result,
          read_code: readCode.trim() || null,
          comment: comment.trim() || null,
        }
        return markingApi.inspect(
          rec.id,
          body,
          keyOf(markingSignature(`inspect:${rec.id}`, body))
        )
      }
      if (act === 'reprint') {
        const body = {
          lot_id: rec.lot_id,
          record_id: rec.id,
          reason_id: reasonId.trim(),
          comment: comment.trim(),
        }
        return markingApi.mark(body, keyOf(markingSignature('mark', body)))
      }
      const body = { reason_id: reasonId.trim(), comment: comment.trim() }
      return markingApi.void(
        rec.id,
        body,
        keyOf(markingSignature(`void:${rec.id}`, body))
      )
    },
    onSuccess: () => {
      toast.success(t(`mes.marking.done.${act}`))
      void qc.invalidateQueries({ queryKey: ['mes', 'marking'] })
      onClose()
    },
    onError: (e) => setErrs({ form: markingErrorMessage(e) }),
  })
  const submit = () => {
    const e: Record<string, string> = {}
    if (act === 'inspect' && readCode.trim()) {
      const bad = traceCodeError(readCode.trim())
      if (bad)
        e.read_code = t(`mes.marking.err.trace_${bad}`, {
          n: TRACE_CODE_RULE.maxLength,
        })
    }
    if (act !== 'inspect') {
      for (const k of reprintErrors({ reason_id: reasonId, comment }))
        e[k === 'comment_too_long' ? 'comment' : k] =
          k === 'comment_too_long'
            ? t('mes.marking.err.commentTooLong', { n: COMMENT_MAX })
            : t(
                `mes.marking.err.${k === 'reason_id' ? 'reason_id' : 'comment'}Required`
              )
    }
    setErrs(e)
    if (Object.keys(e).length) return
    if (act === 'void' && !confirm) {
      setConfirm(true)
      return
    }
    m.mutate()
  }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t(`mes.marking.${act}`)}</DialogTitle>
          <DialogDescription>
            {t(`mes.marking.actHint.${act}`)}
          </DialogDescription>
        </DialogHeader>
        <div className='grid gap-3'>
          {act === 'inspect' && (
            <>
              <div className='flex gap-4'>
                {(['pass', 'fail'] as const).map((r) => (
                  <label key={r} className='flex items-center gap-1 text-sm'>
                    <input
                      type='radio'
                      name='mk-result'
                      checked={result === r}
                      onChange={() => setResult(r)}
                      data-testid={`mk-result-${r}`}
                    />
                    {t(`mes.marking.insp.${r}`)}
                  </label>
                ))}
              </div>
              <div className='grid gap-1'>
                <Label htmlFor='mk-read'>{t('mes.marking.readCode')}</Label>
                <Input
                  id='mk-read'
                  className='font-mono'
                  value={readCode}
                  onChange={(e) => setReadCode(e.target.value)}
                  data-testid='mk-read-code'
                />
                <FieldErr k='read_code' msg={errs.read_code} />
              </div>
            </>
          )}
          {act !== 'inspect' && (
            <div className='grid gap-1'>
              <Label htmlFor='mk-reason'>
                {t('mes.marking.reasonId')}
                <span className='text-destructive'> *</span>
              </Label>
              <Input
                id='mk-reason'
                value={reasonId}
                onChange={(e) => setReasonId(e.target.value)}
                data-testid='mk-reason-id'
              />
              <FieldErr k='reason_id' msg={errs.reason_id} />
            </div>
          )}
          <div className='grid gap-1'>
            <Label htmlFor='mk-comment'>
              {t('mes.marking.comment')}
              {act !== 'inspect' && (
                <span className='text-destructive'> *</span>
              )}
            </Label>
            <Textarea
              id='mk-comment'
              value={comment}
              maxLength={act === 'inspect' ? undefined : COMMENT_MAX + 50}
              onChange={(e) => setComment(e.target.value)}
              data-testid='mk-comment'
            />
            <FieldErr k='comment' msg={errs.comment} />
          </div>
          {confirm && (
            <p
              className='text-sm font-medium text-destructive'
              data-testid='mk-void-confirm'
            >
              {t('mes.marking.voidConfirm', { code: rec.trace_code })}
            </p>
          )}
          <FieldErr k='form' msg={errs.form} />
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            variant={act === 'void' ? 'destructive' : 'default'}
            onClick={submit}
            disabled={m.isPending}
            data-testid='mk-act-ok'
          >
            {confirm ? t('mes.marking.voidConfirmOk') : t('mes.marking.ok')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
