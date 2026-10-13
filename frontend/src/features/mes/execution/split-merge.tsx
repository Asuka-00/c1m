/** 拆批 / 合批卡片与对话框、谱系列表。 */
import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { fmtDateTime, t } from '@/i18n'
import {
  GitFork,
  GitMerge,
  Info,
  Minus,
  Plus,
  Split,
  TriangleAlert,
} from 'lucide-react'
import { toast } from 'sonner'
import {
  blockedResults,
  execApi,
  type CheckResult,
  type ExecContext,
  type GenealogyLink,
  type PrioRef,
  type SmBody,
  type SplitChild,
} from '@/lib/api/mes/execution'
import { cn } from '@/lib/utils'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
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
import { EmptyState } from '@/components/desc-list'
import { IconButton } from '@/components/icon-button'
import { MES_PERM, useMesCan } from '@/features/mes/common/mes-perm'
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesEntity } from '@/features/mes/common/use-mes-meta'
import { CheckPanel } from './exec-parts'
import { type LotPage, lotPageLink } from './lot-links'
import { canMergeLot, canSplitLot, checkSplit } from './lot-rules'

/** 谱系列表：拆批母批 / 子批，合批源批次 / 目标批次。 */
export function GenealogyList({
  lotId,
  links,
  page = 'lot-trace',
}: {
  lotId: string
  links: GenealogyLink[]
  page?: LotPage
}) {
  if (!links.length)
    return <EmptyState icon={GitFork}>{t('mes.sm.noGenealogy')}</EmptyState>
  return (
    <ul className='space-y-1.5 text-sm' data-testid='genealogy'>
      {links.map((g, i) => {
        const isParent = g.parent_id === lotId
        const other = isParent
          ? { id: g.child_id, code: g.child }
          : { id: g.parent_id, code: g.parent }
        const key =
          g.relation === 'split'
            ? isParent
              ? 'splitTo'
              : 'splitFrom'
            : isParent
              ? 'mergedInto'
              : 'mergedFrom'
        const Icon = g.relation === 'split' ? GitFork : GitMerge
        return (
          <li key={i} className='flex flex-wrap items-center gap-x-2'>
            <Icon
              className={cn(
                'size-4',
                g.relation === 'split' ? 'text-sky-600' : 'text-violet-600'
              )}
            />
            <span className='text-muted-foreground'>{t(`mes.sm.${key}`)}</span>
            <Link
              {...lotPageLink(page, other.id)}
              className='font-mono font-medium underline-offset-2 hover:underline'
            >
              {other.code}
            </Link>
            <span>
              {t('mes.exec.qty')} {g.qty}
            </span>
            {g.units.length > 0 && (
              <span
                className='max-w-64 truncate font-mono text-xs text-muted-foreground'
                title={g.units.join(', ')}
              >
                {g.units.join(', ')}
              </span>
            )}
            <span className='text-xs text-muted-foreground'>
              {g.at ? fmtDateTime(g.at) : ''}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

/** 操作台卡片：规则摘要、拆批 / 合批按钮、谱系。 */
export function SplitMergeCard({ cx }: { cx: ExecContext }) {
  const can = useMesCan()
  const [open, setOpen] = useState<'split' | 'merge' | null>(null)
  const sm = cx.sm
  if (!sm) return null
  const r = sm.rule
  const onHold = !!cx.lot.on_hold
  const canSplit =
    can(MES_PERM.execSplit) &&
    canSplitLot(cx.lot) &&
    sm.allowed &&
    !!r?.allow_split
  const canMerge =
    can(MES_PERM.execMerge) &&
    canMergeLot(cx.lot) &&
    sm.allowed &&
    !onHold &&
    !!r?.allow_merge
  return (
    <Card className='gap-3'>
      <CardHeader>
        <CardTitle className='flex items-center gap-2 text-base'>
          <GitFork className='size-4 text-muted-foreground' />
          {t('mes.sm.title')}
        </CardTitle>
        <CardAction className='flex gap-2'>
          <Button
            size='sm'
            variant='outline'
            disabled={!canSplit}
            onClick={() => setOpen('split')}
            data-testid='open-split'
          >
            <Split className='size-4' />
            {t('mes.sm.split')}
          </Button>
          <Button
            size='sm'
            variant='outline'
            disabled={!canMerge}
            onClick={() => setOpen('merge')}
            data-testid='open-merge'
          >
            <GitMerge className='size-4' />
            {t('mes.sm.merge')}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className='space-y-4 text-sm'>
        {r ? (
          <dl className='grid grid-cols-2 gap-x-4 gap-y-2 rounded-md bg-muted/40 p-3 text-xs'>
            <div>
              <dt className='text-muted-foreground'>{t('mes.sm.rule')}</dt>
              <dd className='font-mono font-medium'>{r.code}</dd>
            </div>
            <div>
              <dt className='text-muted-foreground'>{t('mes.sm.allowed')}</dt>
              <dd className='flex flex-wrap gap-1'>
                <Badge variant={r.allow_split ? 'secondary' : 'outline'}>
                  {r.allow_split ? '✓' : '✕'} {t('mes.sm.split')}
                </Badge>
                <Badge variant={r.allow_merge ? 'secondary' : 'outline'}>
                  {r.allow_merge ? '✓' : '✕'} {t('mes.sm.merge')}
                </Badge>
              </dd>
            </div>
            <div>
              <dt className='text-muted-foreground'>{t('mes.sm.maxLots')}</dt>
              <dd className='font-medium'>
                {r.max_children}
                <span className='ms-1 font-normal text-muted-foreground'>
                  ({t('mes.sm.usedLots', { n: r.children + 1 })})
                </span>
              </dd>
            </div>
            <div>
              <dt className='text-muted-foreground'>{t('mes.sm.minQty')}</dt>
              <dd className='font-medium'>{r.min_qty}</dd>
            </div>
          </dl>
        ) : (
          <Alert variant='destructive'>
            <TriangleAlert />
            <AlertDescription>{t('mes.sm.noRule')}</AlertDescription>
          </Alert>
        )}
        {!sm.allowed && (
          <Alert>
            <Info />
            <AlertDescription>{t('mes.sm.stateHint')}</AlertDescription>
          </Alert>
        )}
        <div className='space-y-2'>
          <p className='text-xs font-medium text-muted-foreground'>
            {t('mes.sm.genealogy')}
          </p>
          <GenealogyList
            lotId={String(cx.lot.id)}
            links={sm.genealogy}
            page='lot-console'
          />
        </div>
      </CardContent>
      {open === 'split' && (
        <SplitDialog cx={cx} onClose={() => setOpen(null)} />
      )}
      {open === 'merge' && (
        <MergeDialog cx={cx} onClose={() => setOpen(null)} />
      )}
    </Card>
  )
}

function useSm<T>(
  fn: (body: SmBody) => Promise<T>,
  onDone: (r: T) => void
): {
  results: CheckResult[] | null
  blocked: boolean
  busy: boolean
  run: (body: SmBody) => void
} {
  const { entity } = useMesEntity('lot')
  const [results, setResults] = useState<CheckResult[] | null>(null)
  const [blocked, setBlocked] = useState(false)
  const m = useMutation({
    mutationFn: fn,
    onSuccess: (r, body) => {
      const res = (r as { results?: CheckResult[] }).results ?? []
      setResults(res)
      setBlocked(false)
      if (!body.preview) onDone(r)
    },
    onError: (e) => {
      const b = blockedResults(e)
      if (b) {
        setResults(b)
        setBlocked(true)
        toast.error(t('mes.exec.blocked'))
      } else toast.error(mesErrorMessage(e, entity))
    },
  })
  return { results, blocked, busy: m.isPending, run: (b) => m.mutate(b) }
}

function SplitDialog({
  cx,
  onClose,
}: {
  cx: ExecContext
  onClose: () => void
}) {
  const can = useMesCan()
  const qc = useQueryClient()
  const qtyMode = cx.tracking_level === 'quantity'
  const active = cx.units.filter((u) => u.status !== 'scrapped')
  const [n, setN] = useState(1)
  const [pick, setPick] = useState<Record<string, number>>({}) // 单元 -> 子批序号
  const [qtys, setQtys] = useState<string[]>([''])
  const [comment, setComment] = useState('')
  const lotQty = Number(cx.lot.qty ?? 0)
  const children: SplitChild[] = useMemo(
    () =>
      Array.from({ length: n }, (_, i) =>
        qtyMode
          ? { qty: Number(qtys[i] || 0) }
          : {
              unit_ids: Object.entries(pick)
                .filter(([, c]) => c === i + 1)
                .map(([u]) => u),
            }
      ),
    [n, pick, qtys, qtyMode]
  )
  const { remain, tooMany, ready } = checkSplit(children, lotQty, qtyMode)
  const sm = useSm(
    (body) => execApi.split(String(cx.lot.id), children, { comment, ...body }),
    (r) => {
      toast.success(
        t('mes.sm.splitDone', {
          codes: (r.children ?? []).map((c) => c.code).join(', '),
        })
      )
      qc.invalidateQueries({ queryKey: ['mes'] })
      onClose()
    }
  )
  const setCount = (k: number) => {
    const v = Math.max(1, Math.min(9, k))
    setN(v)
    setQtys((q) => Array.from({ length: v }, (_, i) => q[i] ?? ''))
    setPick((p) =>
      Object.fromEntries(Object.entries(p).filter(([, c]) => c <= v))
    )
  }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>
            {t('mes.sm.split')} · {String(cx.lot.code)}
          </DialogTitle>
          <DialogDescription>
            {t(qtyMode ? 'mes.sm.splitQtyHint' : 'mes.sm.splitUnitHint')}
          </DialogDescription>
        </DialogHeader>
        <div className='flex items-center gap-2 text-sm'>
          <Label>{t('mes.sm.childCount')}</Label>
          <IconButton
            label={t('mes.sm.childMinus')}
            variant='outline'
            className='size-7'
            onClick={() => setCount(n - 1)}
          >
            <Minus className='size-3' />
          </IconButton>
          <span className='w-6 text-center tabular-nums'>{n}</span>
          <IconButton
            label={t('mes.sm.childPlus')}
            variant='outline'
            className='size-7'
            onClick={() => setCount(n + 1)}
            data-testid='child-plus'
          >
            <Plus className='size-3' />
          </IconButton>
          {tooMany ? (
            <span
              className='ms-auto text-destructive'
              data-testid='split-too-many'
            >
              {t('mes.sm.tooMany', { total: lotQty })}
            </span>
          ) : (
            <span className='ms-auto text-muted-foreground'>
              {t('mes.sm.remain', { n: remain, total: lotQty })}
            </span>
          )}
        </div>
        {qtyMode ? (
          <div className='grid grid-cols-3 gap-3'>
            {qtys.map((q, i) => (
              <div key={i} className='grid gap-1'>
                <Label htmlFor={`split-qty-${i}`}>
                  {t('mes.sm.child', { n: i + 1 })}
                  <span className='text-destructive'> *</span>
                </Label>
                <Input
                  id={`split-qty-${i}`}
                  type='number'
                  min={1}
                  value={q}
                  onChange={(e) =>
                    setQtys((x) =>
                      x.map((v, k) => (k === i ? e.target.value : v))
                    )
                  }
                />
              </div>
            ))}
          </div>
        ) : (
          <div className='rounded-md border'>
            <div className='grid grid-cols-[1fr_auto] gap-2 border-b bg-muted/40 px-3 py-1.5 text-xs font-medium'>
              <span>{t('mes.exec.unit')}</span>
              <span>{t('mes.sm.goesTo')}</span>
            </div>
            <ul className='max-h-72 divide-y overflow-y-auto'>
              {active.map((u) => (
                <li
                  key={u.id}
                  className='grid grid-cols-[1fr_auto] items-center gap-2 px-3 py-1'
                >
                  <span className='font-mono text-xs'>
                    {u.slot != null && `#${u.slot} `}
                    {u.code}
                  </span>
                  <div className='flex gap-1'>
                    {[0, ...Array.from({ length: n }, (_, i) => i + 1)].map(
                      (c) => (
                        <button
                          key={c}
                          type='button'
                          data-testid={`pick-${u.code}-${c}`}
                          onClick={() =>
                            setPick((p) => {
                              const x = { ...p }
                              if (c) x[u.id] = c
                              else delete x[u.id]
                              return x
                            })
                          }
                          className={cn(
                            'h-6 min-w-8 rounded border px-1.5 text-xs',
                            (pick[u.id] ?? 0) === c
                              ? c
                                ? 'border-sky-600 bg-sky-600 text-white'
                                : 'bg-muted font-medium'
                              : 'text-muted-foreground hover:bg-muted'
                          )}
                        >
                          {c
                            ? t('mes.sm.childShort', { n: c })
                            : t('mes.sm.keep')}
                        </button>
                      )
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className='grid gap-1'>
          <Label htmlFor='split-comment'>{t('mes.exec.comment')}</Label>
          <Textarea
            id='split-comment'
            rows={2}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>
        <CheckPanel
          results={sm.results}
          blocked={sm.blocked}
          canOverride={can(MES_PERM.execOverride)}
          busy={sm.busy}
          onOverride={(reason) =>
            sm.run({ override: true, override_reason: reason })
          }
        />
        <DialogFooter>
          <Button
            variant='outline'
            disabled={!ready || sm.busy}
            onClick={() => sm.run({ preview: true })}
          >
            {t('mes.exec.preview')}
          </Button>
          <Button
            disabled={!ready || sm.busy}
            onClick={() => sm.run({})}
            data-testid='do-split'
          >
            <Split className='size-4' />
            {t('mes.sm.split')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function MergeDialog({
  cx,
  onClose,
}: {
  cx: ExecContext
  onClose: () => void
}) {
  const can = useMesCan()
  const qc = useQueryClient()
  const cands = cx.sm?.candidates ?? []
  const [sel, setSel] = useState<string[]>([])
  const [comment, setComment] = useState('')
  const total =
    Number(cx.lot.qty ?? 0) +
    cands.filter((c) => sel.includes(c.id)).reduce((a, c) => a + c.qty, 0)
  const prios = [
    cx.sm?.priority,
    ...cands.filter((c) => sel.includes(c.id)).map((c) => c.priority),
  ].filter((p): p is PrioRef => !!p)
  const best = prios.reduce<PrioRef | null>(
    (a, p) => (!a || p.level < a.level ? p : a),
    null
  )
  const changed = !!best && best.id !== cx.sm?.priority?.id
  const sm = useSm(
    (body) => execApi.merge(String(cx.lot.id), sel, { comment, ...body }),
    (r) => {
      toast.success(
        t('mes.sm.mergeDone', {
          codes: (r.merged ?? []).map((c) => c.code).join(', '),
        })
      )
      qc.invalidateQueries({ queryKey: ['mes'] })
      onClose()
    }
  )
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>
            {t('mes.sm.merge')} → {String(cx.lot.code)}
          </DialogTitle>
          <DialogDescription>{t('mes.sm.mergeHint')}</DialogDescription>
        </DialogHeader>
        {cands.length === 0 ? (
          <p className='text-sm text-muted-foreground'>
            {t('mes.sm.noCandidates')}
          </p>
        ) : (
          <ul className='divide-y rounded-md border text-sm'>
            {cands.map((c) => {
              const bad = c.problems.length > 0 || c.on_hold
              return (
                <li key={c.id} className='flex items-start gap-3 px-3 py-2'>
                  <Checkbox
                    id={`m-${c.id}`}
                    disabled={bad}
                    checked={sel.includes(c.id)}
                    onCheckedChange={(v) =>
                      setSel((s) =>
                        v ? [...s, c.id] : s.filter((x) => x !== c.id)
                      )
                    }
                  />
                  <div className='min-w-0 flex-1'>
                    <label
                      htmlFor={`m-${c.id}`}
                      className='flex items-center gap-2 font-mono font-medium'
                    >
                      {c.code}
                      <span className='font-sans font-normal text-muted-foreground'>
                        {t('mes.exec.qty')} {c.qty}
                      </span>
                      {c.priority && <PrioBadge p={c.priority} />}
                      {c.on_hold && (
                        <Badge variant='destructive'>
                          {t('mes.exec.onHold')}
                        </Badge>
                      )}
                    </label>
                    {c.problems.length > 0 && (
                      <ul className='list-disc ps-4 text-xs text-destructive'>
                        {c.problems.map((x, k) => (
                          <li key={k}>{x}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
        <p className='flex flex-wrap items-center gap-2 text-sm'>
          {t('mes.sm.resultPriority')}
          {best ? <PrioBadge p={best} /> : '—'}
          {changed && cx.sm?.priority && (
            <span className='text-xs text-muted-foreground'>
              {t('mes.sm.prioChange', { from: cx.sm.priority.code })}
            </span>
          )}
        </p>
        <p className='text-sm'>
          {t('mes.sm.mergedQty', { n: total })} ·{' '}
          <span className='text-muted-foreground'>{t('mes.sm.qtimeNote')}</span>
        </p>
        <div className='grid gap-1'>
          <Label htmlFor='merge-comment'>{t('mes.exec.comment')}</Label>
          <Textarea
            id='merge-comment'
            rows={2}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>
        <CheckPanel
          results={sm.results}
          blocked={sm.blocked}
          canOverride={can(MES_PERM.execOverride)}
          busy={sm.busy}
          onOverride={(reason) =>
            sm.run({ override: true, override_reason: reason })
          }
        />
        <DialogFooter>
          <Button
            variant='outline'
            disabled={!sel.length || sm.busy}
            onClick={() => sm.run({ preview: true })}
          >
            {t('mes.exec.preview')}
          </Button>
          <Button
            disabled={!sel.length || sm.busy}
            onClick={() => sm.run({})}
            data-testid='do-merge'
          >
            <GitMerge className='size-4' />
            {t('mes.sm.merge')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function PrioBadge({ p }: { p: PrioRef }) {
  return (
    <Badge
      variant='outline'
      className='font-sans font-normal'
      style={p.color ? { borderColor: p.color, color: p.color } : undefined}
    >
      {p.code} · {p.name}
    </Badge>
  )
}
