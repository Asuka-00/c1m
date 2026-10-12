/** 批次操作台页面：批次头部信息、阶段步骤条、作业面板、检查 / Hold / 拆合批卡片。 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useSearch } from '@tanstack/react-router'
import { fmtDateTime, t } from '@/i18n'
import {
  CircleCheck,
  History,
  Info,
  ListChecks,
  Loader2,
  PauseCircle,
  PlayCircle,
  Plus,
  RefreshCw,
  SearchCheck,
  Timer,
  Trash2,
} from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import {
  blockedResults,
  execApi,
  type CheckResult,
  type ExecContext,
  type ExecStage,
  type StageBody,
} from '@/lib/api/mes/execution'
import { splitLabel } from '@/lib/split-label'
import { cn } from '@/lib/utils'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
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
import { DescItem, DescList, EmptyState } from '@/components/desc-list'
import { enumLabel, optLabel } from '@/features/mes/common/labels'
import { RefSelect } from '@/features/mes/common/ref-select'
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesEntity, useMesMeta } from '@/features/mes/common/use-mes-meta'
import { CheckPanel, Pick, StageBar } from './exec-parts'
import { SplitMergeCard } from './split-merge'
import { WipActionsCard } from './wip-actions'

type Dc = Record<string, string> // `${item}|${unit}|${site}` -> 录入值
type Scrap = { unit_id?: string; qty?: string; reason_id: string }

/** 批次操作台：选择批次，填写输入并执行下一阶段。 */
export default function LotConsolePage() {
  const search = useSearch({ strict: false }) as Record<string, unknown>
  const nav = useNavigate()
  const lotId = (search.lot as string) || ''
  const tk = useTenantKey()
  const { data: meta } = useMesMeta()
  const perms = meta?.perms ?? []
  const ctx = useQuery({
    queryKey: ['mes', 'exec', tk, lotId],
    queryFn: () => execApi.context(lotId),
    enabled: !!lotId,
  })
  const setLot = (id: string | null) =>
    nav({
      to: '/$',
      params: { _splat: 'mes/lot-console' },
      search: (id ? { lot: id } : {}) as never,
    })
  return (
    <Page
      title={t('menu.mes-lot-console')}
      description={t('mes.exec.consoleHint')}
      actions={
        lotId && (
          <Button variant='outline' asChild>
            <Link
              to='/$'
              params={{ _splat: 'mes/lot-trace' }}
              search={{ lot: lotId } as never}
            >
              <History className='size-4' />
              {t('menu.mes-lot-trace')}
            </Link>
          </Button>
        )
      }
    >
      <div className='flex max-w-xl items-center gap-2'>
        <Label className='shrink-0'>{t('mes.entity.lot')}</Label>
        <RefSelect
          id='console-lot'
          target='lot'
          value={lotId || null}
          label={ctx.data ? String(ctx.data.lot.code) : null}
          onChange={(id) => setLot(id)}
        />
        {lotId && (
          <Button
            size='icon'
            variant='ghost'
            aria-label={t('mes.exec.refresh')}
            onClick={() => ctx.refetch()}
          >
            <RefreshCw className='size-4' />
          </Button>
        )}
      </div>
      {!lotId && (
        <p className='text-muted-foreground'>{t('mes.exec.pickLot')}</p>
      )}
      {ctx.isLoading && <Loader2 className='animate-spin' />}
      {ctx.data && (
        <Console
          key={`${lotId}-${ctx.dataUpdatedAt}`}
          cx={ctx.data}
          perms={perms}
        />
      )}
    </Page>
  )
}

function Console({ cx, perms }: { cx: ExecContext; perms: string[] }) {
  const qc = useQueryClient()
  const { entity: lotE } = useMesEntity('lot')
  const lot = cx.lot
  const stage = cx.next_stage
  const xc = cx.exec_ctx as Record<string, unknown>
  const [equipment, setEquipment] = useState(String(lot.equipment_id ?? ''))
  const [recipe, setRecipe] = useState(
    String(lot.recipe_id ?? (cx.recipes?.length === 1 ? cx.recipes[0].id : ''))
  )
  const [eqpRecipe, setEqpRecipe] = useState('')
  const [reticle, setReticle] = useState(
    String(
      xc.reticle_id ?? (cx.reticles?.length === 1 ? cx.reticles[0].id : '')
    )
  )
  const [carrier, setCarrier] = useState<string | null>(
    (lot.carrier_id as string) ?? null
  )
  const [tools, setTools] = useState<Record<string, string>>(() => {
    // 默认：已上机的工具（Track Out）或第一个可用工具
    const ids = (xc.tool_ids as string[]) ?? []
    const out: Record<string, string> = {}
    for (const g of cx.tools ?? []) {
      const cur = g.options.find((o) => ids.includes(o.id))
      const ok = g.options.find((o) => o.status === 'available')
      if (g.fixture) out[g.fixture.id] = (cur ?? ok)?.id ?? ''
    }
    return out
  })
  const [mats, setMats] = useState<string[]>(
    (xc.material_lot_ids as string[]) ?? []
  )
  const [dc, setDc] = useState<Dc>({})
  const [scrap, setScrap] = useState<Scrap[]>([])
  const [rework, setRework] = useState<Record<string, string>>({})
  const [branch, setBranch] = useState(false)
  const [doRework, setDoRework] = useState(!!lot.pending_rework)
  const [results, setResults] = useState<CheckResult[] | null>(null)
  const [blocked, setBlocked] = useState(false)
  const [holdOpen, setHoldOpen] = useState(false)

  const qty = cx.tracking_level === 'quantity'
  const activeUnits = cx.units.filter((u) => u.status !== 'scrapped')
  const body = (): StageBody => {
    const b: StageBody = {}
    if (stage === 'move_in' || stage === 'track_in')
      b.equipment_id = equipment || null
    if (stage === 'track_in') {
      b.recipe_id = recipe || null
      b.eqp_recipe = eqpRecipe.trim() || null
      b.reticle_id = reticle || null
      b.carrier_id = carrier
      b.tool_ids = Object.values(tools).filter(Boolean)
      b.material_lot_ids = mats
    }
    if (stage === 'track_out') {
      b.material_lot_ids = mats
      b.dc = Object.entries(dc)
        .filter(([, v]) => v !== '' && !Number.isNaN(Number(v)))
        .map(([k, v]) => {
          const [item, unit, site] = k.split('|')
          return {
            measurement_item_id: item,
            unit_id: unit || null,
            site_no: Number(site),
            value: Number(v),
          }
        })
      b.scrap = scrap
        .filter((s) => s.reason_id && (s.unit_id || Number(s.qty) > 0))
        .map((s) =>
          qty
            ? { reason_id: s.reason_id, qty: Number(s.qty) }
            : { reason_id: s.reason_id, unit_id: s.unit_id }
        )
      b.rework_units = Object.entries(rework)
        .filter(([, r]) => r)
        .map(([unit_id, reason_id]) => ({ unit_id, reason_id }))
    }
    if (stage === 'move_out') {
      b.branch = branch
      b.rework = doRework
    }
    return b
  }
  const run = useMutation({
    mutationFn: (o: { override?: string }) =>
      execApi.stage(
        String(lot.id),
        stage as ExecStage,
        o.override
          ? { ...body(), override: true, override_reason: o.override }
          : body()
      ),
    onSuccess: (r) => {
      const auto = (r.auto ?? []).filter((a) => a.ok).map((a) => a.stage)
      toast.success(
        [
          t(`mes.exec.done.${stage}`),
          ...auto.map((s) =>
            t('mes.exec.autoDone', { stage: t(`mes.exec.stage.${s}`) })
          ),
          r.qtime && t(`mes.exec.qtimeAction.${r.qtime}`),
          r.lot?.on_hold && t('mes.exec.nowOnHold'),
        ]
          .filter(Boolean)
          .join(' · ')
      )
      qc.invalidateQueries({ queryKey: ['mes'] })
    },
    onError: (e) => {
      const res = blockedResults(e)
      if (res) {
        setResults(res)
        setBlocked(true)
        toast.error(t('mes.exec.blocked'))
      } else toast.error(mesErrorMessage(e, lotE))
    },
  })
  const preview = useMutation({
    mutationFn: () =>
      execApi.preview(String(lot.id), stage as ExecStage, body()),
    onSuccess: (r) => {
      setResults(r.results)
      setBlocked(false)
    },
    onError: (e) => toast.error(mesErrorMessage(e, lotE)),
  })
  const step = cx.step
  const terminal = !stage
  const onHold = !!lot.on_hold
  const canRun = perms.includes('mes.exec:write') && !terminal && !onHold
  const [stepCode, stepName] = splitLabel(
    step?.operation ? optLabel(step.operation) : ''
  )
  const [eqCode, eqName] = splitLabel(lot.equipment_label)
  const [rcCode, rcName] = splitLabel(lot.recipe_label)
  const [prCode, prName] = splitLabel(lot.product_label)
  const [woCode] = splitLabel(lot.work_order_label)
  const route = step?.route ?? ''
  const rv = route.match(/^(.*) (v\d+)$/)
  const qtimeBad = (cx.qtime ?? []).some((q) => q.exceeded || q.too_early)
  return (
    <div
      className='grid items-start gap-4 min-[1100px]:grid-cols-[minmax(0,1fr)_minmax(320px,380px)]'
      data-testid='console'
    >
      <div className='min-w-0 space-y-4'>
        <Card className='gap-4'>
          <CardHeader className='gap-2'>
            <div className='flex flex-wrap items-center gap-2'>
              <CardTitle className='font-mono text-xl'>
                {String(lot.code)}
              </CardTitle>
              <Badge variant='outline'>
                {enumLabel('lot_status', String(lot.lot_status))}
              </Badge>
              {onHold && (
                <Badge variant='destructive'>
                  <PauseCircle className='size-3' />
                  {t('mes.exec.onHold')}
                </Badge>
              )}
              <Badge variant='secondary'>
                {enumLabel('tracking_level', cx.tracking_level)}
              </Badge>
              {!!lot.pending_rework && (
                <Badge className='bg-amber-500'>
                  {t('mes.exec.pendingRework')}
                </Badge>
              )}
            </div>
          </CardHeader>
          <CardContent className='space-y-5'>
            <DescList>
              <DescItem
                label={t('mes.exec.step')}
                value={step ? `${step.seq} · ${stepCode || '—'}` : '—'}
                sub={stepName}
              />
              <DescItem
                label={t('mes.exec.route')}
                value={rv ? rv[1] : route || '—'}
                sub={rv ? rv[2] : undefined}
              />
              <DescItem
                label={t('mes.entity.product')}
                value={prCode}
                sub={prName}
              />
              <DescItem
                label={t('mes.exec.qty')}
                value={
                  <>
                    {String(lot.qty)}
                    {Number(lot.scrapped_qty) > 0 && (
                      <span className='ms-1 font-normal text-destructive'>
                        (−{String(lot.scrapped_qty)})
                      </span>
                    )}
                  </>
                }
                sub={woCode || undefined}
              />
              <DescItem
                label={t('mes.exec.equipment')}
                value={eqCode || '—'}
                sub={eqName}
              />
              <DescItem
                label={t('mes.exec.recipe')}
                value={rcCode || '—'}
                sub={rcName}
              />
              <DescItem
                label={t('mes.exec.lastAction')}
                value={lot.stage_at ? fmtDateTime(String(lot.stage_at)) : '—'}
              />
            </DescList>
            <StageBar
              next={stage}
              status={String(lot.lot_status)}
              auto={step?.auto}
            />
            {cx.stack.length > 0 && (
              <Alert>
                <Info />
                <AlertDescription>
                  {t('mes.exec.inSubRoute', {
                    kind: t(
                      `mes.exec.frame.${cx.stack[cx.stack.length - 1].kind}`
                    ),
                  })}
                </AlertDescription>
              </Alert>
            )}
            {(cx.qtime ?? []).length > 0 && (
              <Alert variant={qtimeBad ? 'destructive' : 'default'}>
                <Timer />
                <AlertTitle>Q-Time</AlertTitle>
                <AlertDescription>
                  {(cx.qtime ?? []).map((q) => (
                    <span key={q.rule} className='block'>
                      {q.rule}: {q.minutes} min
                      {q.min != null && ` · min ${q.min}`}
                      {q.max != null && ` · max ${q.max}`}
                    </span>
                  ))}
                </AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>

        {!terminal ? (
          <Card className='gap-4' data-testid='action-panel'>
            <CardHeader>
              <CardDescription>{t('mes.exec.nextAction')}</CardDescription>
              <CardTitle className='text-lg'>
                {t(`mes.exec.stage.${stage}`)}
              </CardTitle>
            </CardHeader>
            <CardContent className='space-y-4'>
              {onHold && (
                <Alert variant='destructive'>
                  <PauseCircle />
                  <AlertTitle>{t('mes.exec.onHold')}</AlertTitle>
                  <AlertDescription>
                    {t('mes.exec.holdBlocks')}
                  </AlertDescription>
                </Alert>
              )}
              {(stage === 'move_in' || stage === 'track_in') && (
                <div className='grid gap-4 sm:grid-cols-2'>
                  <Pick
                    id='ex-eqp'
                    label={t('mes.exec.equipment')}
                    required={
                      stage === 'track_in' && (cx.equipment?.length ?? 0) > 0
                    }
                    value={equipment}
                    onChange={setEquipment}
                    options={(cx.equipment ?? []).map((e) => ({
                      id: e.id,
                      label: (
                        <span className='flex items-center gap-2'>
                          <span
                            className='inline-block size-2.5 rounded-full'
                            style={{ background: e.color ?? '#999' }}
                          />
                          {optLabel(e)}
                          <span className='text-xs text-muted-foreground'>
                            {e.state}
                          </span>
                        </span>
                      ),
                    }))}
                  />
                </div>
              )}
              {stage === 'track_in' && (
                <TrackInInputs
                  cx={cx}
                  recipe={recipe}
                  setRecipe={setRecipe}
                  eqpRecipe={eqpRecipe}
                  setEqpRecipe={setEqpRecipe}
                  reticle={reticle}
                  setReticle={setReticle}
                  carrier={carrier}
                  setCarrier={setCarrier}
                  tools={tools}
                  setTools={setTools}
                  mats={mats}
                  setMats={setMats}
                />
              )}
              {stage === 'track_out' && (
                <TrackOutInputs
                  cx={cx}
                  qty={qty}
                  units={activeUnits}
                  dc={dc}
                  setDc={setDc}
                  scrap={scrap}
                  setScrap={setScrap}
                  rework={rework}
                  setRework={setRework}
                  mats={mats}
                  setMats={setMats}
                />
              )}
              {stage === 'move_out' && (
                <div className='space-y-3 text-sm'>
                  <p className='text-muted-foreground'>
                    {step?.is_last
                      ? t('mes.exec.lastStep')
                      : t('mes.exec.nextStepHint')}
                  </p>
                  {step?.branch_to_seq != null && (
                    <label className='flex items-center gap-2'>
                      <Checkbox
                        checked={branch}
                        onCheckedChange={(v) => setBranch(!!v)}
                        disabled={doRework}
                      />
                      {t('mes.exec.takeBranch', {
                        seq: step.branch_to_seq,
                        cond: step.branch_condition ?? '',
                      })}
                    </label>
                  )}
                  {step?.rework_route && (
                    <label className='flex items-center gap-2'>
                      <Checkbox
                        checked={doRework}
                        onCheckedChange={(v) => setDoRework(!!v)}
                      />
                      {t('mes.exec.toRework', { route: step.rework_route })}
                    </label>
                  )}
                </div>
              )}
            </CardContent>
            <CardFooter className='flex flex-wrap justify-end gap-2 border-t'>
              <Button
                variant='outline'
                disabled={preview.isPending}
                data-testid='preview-stage'
                onClick={() => preview.mutate()}
              >
                <SearchCheck className='size-4' />
                {t('mes.exec.preview')}
              </Button>
              <Button
                disabled={!canRun || run.isPending}
                onClick={() => run.mutate({})}
                data-testid='run-stage'
              >
                {run.isPending ? (
                  <Loader2 className='size-4 animate-spin' />
                ) : (
                  <PlayCircle className='size-4' />
                )}
                {t(`mes.exec.stage.${stage}`)}
              </Button>
            </CardFooter>
          </Card>
        ) : (
          <Alert>
            <CircleCheck />
            <AlertDescription>
              {t('mes.exec.terminal', {
                status: enumLabel('lot_status', String(lot.lot_status)),
              })}
            </AlertDescription>
          </Alert>
        )}
      </div>

      <div className='min-w-0 space-y-4'>
        <Card className='gap-3'>
          <CardHeader>
            <CardTitle className='flex items-center gap-2 text-base'>
              <ListChecks className='size-4 text-muted-foreground' />
              {t('mes.exec.checks')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {results ? (
              <CheckPanel
                results={results}
                blocked={blocked}
                canOverride={perms.includes('mes.exec:override')}
                busy={run.isPending}
                onOverride={(reason) => run.mutate({ override: reason })}
              />
            ) : (
              <EmptyState icon={SearchCheck}>
                {t('mes.exec.checksHint')}
              </EmptyState>
            )}
          </CardContent>
        </Card>
        <Card className='gap-3'>
          <CardHeader>
            <CardTitle className='flex items-center gap-2 text-base'>
              <PauseCircle className='size-4 text-muted-foreground' />
              {t('menu.mes-lot_hold')}
            </CardTitle>
            {perms.includes('mes.exec:hold') && !terminal && (
              <CardAction>
                <Button
                  size='sm'
                  variant='outline'
                  data-testid='open-hold'
                  onClick={() => setHoldOpen(true)}
                >
                  {t('mes.exec.hold')}
                </Button>
              </CardAction>
            )}
          </CardHeader>
          <CardContent className='space-y-2 text-sm'>
            {cx.holds.length === 0 && (
              <EmptyState icon={CircleCheck}>
                {t('mes.exec.noHolds')}
              </EmptyState>
            )}
            {cx.holds.map((h) => (
              <HoldRow key={String(h.id)} h={h} cx={cx} perms={perms} />
            ))}
          </CardContent>
        </Card>
        <SplitMergeCard cx={cx} perms={perms} />
        <WipActionsCard cx={cx} perms={perms} />
      </div>
      <HoldDialog cx={cx} open={holdOpen} onOpenChange={setHoldOpen} />
    </div>
  )
}

function TrackInInputs(p: {
  cx: ExecContext
  recipe: string
  setRecipe: (v: string) => void
  eqpRecipe: string
  setEqpRecipe: (v: string) => void
  reticle: string
  setReticle: (v: string) => void
  carrier: string | null
  setCarrier: (v: string | null) => void
  tools: Record<string, string>
  setTools: (v: Record<string, string>) => void
  mats: string[]
  setMats: (v: string[]) => void
}) {
  const { cx } = p
  return (
    <div className='space-y-3'>
      <div className='grid gap-3 sm:grid-cols-2'>
        <Pick
          id='ex-recipe'
          label={t('mes.exec.recipe')}
          required={(cx.recipes?.length ?? 0) > 0}
          value={p.recipe}
          onChange={p.setRecipe}
          options={(cx.recipes ?? []).map((r) => ({
            id: r.id,
            label: `${optLabel(r)} v${r.version} (${enumLabel('status', r.status)})`,
          }))}
        />
        <div className='grid gap-1'>
          <Label htmlFor='ex-eqp-recipe'>{t('mes.exec.eqpRecipe')}</Label>
          <Input
            id='ex-eqp-recipe'
            placeholder={t('mes.exec.eqpRecipeHint')}
            value={p.eqpRecipe}
            onChange={(e) => p.setEqpRecipe(e.target.value)}
          />
        </div>
        {(cx.reticles?.length ?? 0) > 0 && (
          <Pick
            id='ex-reticle'
            label={t('mes.exec.reticle')}
            required
            value={p.reticle}
            onChange={p.setReticle}
            options={(cx.reticles ?? []).map((r) => ({
              id: r.id,
              label: `${r.code} (${enumLabel('asset_status', r.status)})`,
            }))}
          />
        )}
        <div className='grid gap-1'>
          <Label>{t('mes.exec.carrier')}</Label>
          <RefSelect
            target='carrier'
            value={p.carrier}
            label={String(cx.lot.carrier_label ?? '') || null}
            onChange={(id) => p.setCarrier(id)}
          />
        </div>
        {(cx.tools ?? []).map((g) =>
          g.fixture ? (
            <Pick
              key={g.fixture.id}
              id={`ex-tool-${g.fixture.code}`}
              label={`${t('mes.exec.tool')} · ${g.fixture.code}`}
              required
              value={p.tools[g.fixture.id] ?? ''}
              onChange={(v) => p.setTools({ ...p.tools, [g.fixture!.id]: v })}
              options={g.options.map((o) => ({
                id: o.id,
                label: `${o.code} · ${o.usage}/${o.max ?? '∞'} · ${enumLabel('tool_status', o.status)}`,
              }))}
            />
          ) : null
        )}
      </div>
      <MaterialPick cx={cx} mats={p.mats} setMats={p.setMats} />
    </div>
  )
}

function MaterialPick({
  cx,
  mats,
  setMats,
}: {
  cx: ExecContext
  mats: string[]
  setMats: (v: string[]) => void
}) {
  if (!cx.materials?.length) return null
  return (
    <div className='space-y-2'>
      <p className='text-sm font-medium'>{t('mes.exec.materials')}</p>
      {cx.materials.map((m) => (
        <div key={m.material_id} className='rounded-md border p-2 text-sm'>
          <div className='font-medium'>
            {m.material}: {m.need} {m.uom ?? ''}{' '}
            <span className='text-xs text-muted-foreground'>
              ({enumLabel('qty_basis', m.basis)})
            </span>
          </div>
          {m.options.length === 0 && (
            <p className='text-destructive'>{t('mes.exec.noMaterial')}</p>
          )}
          {m.options.map((o) => (
            <label key={o.id} className='flex items-center gap-2'>
              <Checkbox
                checked={mats.includes(o.id)}
                onCheckedChange={(v) =>
                  setMats(v ? [...mats, o.id] : mats.filter((x) => x !== o.id))
                }
              />
              {o.code} · {o.qty} · {o.location ?? ''}{' '}
              {o.expiry && (
                <span className='text-muted-foreground'>({o.expiry})</span>
              )}
            </label>
          ))}
          <p className='text-xs text-muted-foreground'>{t('mes.exec.fefo')}</p>
        </div>
      ))}
    </div>
  )
}

function TrackOutInputs(p: {
  cx: ExecContext
  qty: boolean
  units: ExecContext['units']
  dc: Dc
  setDc: (v: Dc) => void
  scrap: Scrap[]
  setScrap: (v: Scrap[]) => void
  rework: Record<string, string>
  setRework: (v: Record<string, string>) => void
  mats: string[]
  setMats: (v: string[]) => void
}) {
  const { cx } = p
  const dc = cx.dc
  const units = useMemo(
    () =>
      dc?.unit_ids?.length
        ? p.units.filter((u) => dc.unit_ids?.includes(u.id))
        : [null],
    [dc, p.units]
  )
  const scrapReasons = cx.reasons.scrap.map((r) => ({
    id: r.id,
    label: optLabel(r),
  }))
  return (
    <div className='space-y-4'>
      <section className='space-y-2' data-testid='dc-entry'>
        <div>
          <h4 className='text-sm font-semibold'>{t('mes.exec.dc')}</h4>
          <p className='text-xs text-muted-foreground'>
            {dc?.dc_plan ? `${dc.dc_plan} · ` : ''}
            {dc?.message}
          </p>
        </div>
        {dc?.sampled && dc.items.length > 0 ? (
          <div className='overflow-hidden rounded-md border'>
            <Table>
              <TableHeader className='bg-muted/40'>
                <TableRow>
                  <TableHead>{t('mes.exec.item')}</TableHead>
                  <TableHead>{t('mes.exec.unit')}</TableHead>
                  <TableHead>{t('mes.exec.values')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {dc.items.flatMap((it) =>
                  units.map((u) => (
                    <TableRow
                      key={`${it.measurement_item_id}-${u?.id ?? 'lot'}`}
                    >
                      <TableCell className='align-top'>
                        <div className='font-medium'>{it.code}</div>
                        <div className='text-xs text-muted-foreground'>
                          {it.lsl ?? '−∞'} … {it.usl ?? '∞'}
                        </div>
                        <div className='text-xs text-muted-foreground'>
                          {t('mes.exec.oosAction')}:{' '}
                          {enumLabel('oos_action', it.oos_action)}
                        </div>
                      </TableCell>
                      <TableCell className='align-top font-mono text-xs'>
                        {u ? u.code : t('mes.exec.lotLevel')}
                      </TableCell>
                      <TableCell className='whitespace-normal'>
                        <div className='flex flex-wrap gap-1.5'>
                          {Array.from(
                            { length: Math.min(it.sites ?? 1, 5) || 1 },
                            (_, s) => {
                              const k = `${it.measurement_item_id}|${u?.id ?? ''}|${s + 1}`
                              const v = p.dc[k] ?? ''
                              const n = Number(v)
                              const oos =
                                v !== '' &&
                                ((it.lsl != null && n < it.lsl) ||
                                  (it.usl != null && n > it.usl))
                              return (
                                <Input
                                  key={k}
                                  aria-label={`${it.code} ${s + 1}`}
                                  placeholder={`#${s + 1}`}
                                  className={cn(
                                    'h-8 w-20',
                                    oos && 'border-destructive text-destructive'
                                  )}
                                  inputMode='decimal'
                                  value={v}
                                  onChange={(e) =>
                                    p.setDc({ ...p.dc, [k]: e.target.value })
                                  }
                                />
                              )
                            }
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        ) : (
          <p className='text-sm text-muted-foreground'>{t('mes.exec.noDc')}</p>
        )}
      </section>

      <section className='space-y-2' data-testid='scrap-entry'>
        <h4 className='text-sm font-semibold'>
          {p.qty ? t('mes.exec.scrapQty') : t('mes.exec.scrapUnits')}
        </h4>
        {p.qty ? (
          <>
            {p.scrap.map((s, i) => (
              <div key={i} className='flex items-end gap-2'>
                <div className='grid gap-1'>
                  <Label htmlFor={`sq-${i}`}>{t('mes.exec.qty')}</Label>
                  <Input
                    id={`sq-${i}`}
                    className='w-24'
                    inputMode='numeric'
                    value={s.qty ?? ''}
                    onChange={(e) =>
                      p.setScrap(
                        p.scrap.map((x, j) =>
                          j === i ? { ...x, qty: e.target.value } : x
                        )
                      )
                    }
                  />
                </div>
                <div className='w-64'>
                  <Pick
                    id={`sr-${i}`}
                    label={t('mes.exec.reason')}
                    required
                    value={s.reason_id}
                    onChange={(v) =>
                      p.setScrap(
                        p.scrap.map((x, j) =>
                          j === i ? { ...x, reason_id: v } : x
                        )
                      )
                    }
                    options={scrapReasons}
                  />
                </div>
                <Button
                  size='icon'
                  variant='ghost'
                  aria-label={t('common.delete')}
                  onClick={() => p.setScrap(p.scrap.filter((_, j) => j !== i))}
                >
                  <Trash2 className='size-4' />
                </Button>
              </div>
            ))}
            <Button
              size='sm'
              variant='outline'
              onClick={() =>
                p.setScrap([...p.scrap, { qty: '', reason_id: '' }])
              }
            >
              <Plus className='size-4' />
              {t('mes.exec.addScrap')}
            </Button>
            <p className='text-xs text-muted-foreground'>
              {t('mes.exec.goodQty', {
                good:
                  Number(cx.lot.qty) -
                  p.scrap.reduce((a, s) => a + (Number(s.qty) || 0), 0),
              })}
            </p>
          </>
        ) : (
          <div className='max-h-80 overflow-y-auto rounded-md border'>
            <Table>
              <TableHeader className='sticky top-0 z-10 bg-muted'>
                <TableRow>
                  <TableHead className='w-14'>{t('mes.exec.slot')}</TableHead>
                  <TableHead>{t('mes.exec.unit')}</TableHead>
                  <TableHead>{t('mes.exec.disposition')}</TableHead>
                  {cx.reasons.rework.length > 0 && (
                    <TableHead>{t('mes.exec.rework')}</TableHead>
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {p.units.map((u) => {
                  const s = p.scrap.find((x) => x.unit_id === u.id)
                  return (
                    <TableRow key={u.id}>
                      <TableCell className='text-muted-foreground tabular-nums'>
                        {u.slot ?? '—'}
                      </TableCell>
                      <TableCell className='font-mono text-xs'>
                        {u.code}
                      </TableCell>
                      <TableCell className='py-1'>
                        <select
                          aria-label={`${u.code} scrap`}
                          className='h-8 w-full min-w-28 rounded-md border border-input bg-transparent px-2 text-sm'
                          value={s?.reason_id ?? ''}
                          onChange={(e) => {
                            const rest = p.scrap.filter(
                              (x) => x.unit_id !== u.id
                            )
                            p.setScrap(
                              e.target.value
                                ? [
                                    ...rest,
                                    {
                                      unit_id: u.id,
                                      reason_id: e.target.value,
                                    },
                                  ]
                                : rest
                            )
                          }}
                        >
                          <option value=''>{t('mes.exec.good')}</option>
                          {cx.reasons.scrap.map((r) => (
                            <option key={r.id} value={r.id}>
                              {t('mes.exec.scrap')}: {r.code}
                            </option>
                          ))}
                        </select>
                      </TableCell>
                      {cx.reasons.rework.length > 0 && (
                        <TableCell className='py-1'>
                          <select
                            aria-label={`${u.code} rework`}
                            className='h-8 w-full min-w-28 rounded-md border border-input bg-transparent px-2 text-sm'
                            value={p.rework[u.id] ?? ''}
                            disabled={!!s}
                            onChange={(e) =>
                              p.setRework({
                                ...p.rework,
                                [u.id]: e.target.value,
                              })
                            }
                          >
                            <option value=''>—</option>
                            {cx.reasons.rework.map((r) => (
                              <option key={r.id} value={r.id}>
                                {r.code}
                              </option>
                            ))}
                          </select>
                        </TableCell>
                      )}
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </section>
      <MaterialPick cx={cx} mats={p.mats} setMats={p.setMats} />
    </div>
  )
}

function HoldRow({
  h,
  cx,
  perms,
}: {
  h: ExecContext['holds'][number]
  cx: ExecContext
  perms: string[]
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className='rounded-md border p-2'>
      <div className='flex items-center justify-between gap-2'>
        <span className='font-medium'>{String(h.reason_label ?? '')}</span>
        <Badge variant='outline'>
          {enumLabel('hold_type', String(h.hold_type))}
        </Badge>
      </div>
      <div className='text-xs text-muted-foreground'>
        {fmtDateTime(String(h.held_at))} · {String(h.held_by ?? '')} ·{' '}
        {String(h.source ?? '')}
      </div>
      {!!h.comment && <div className='text-xs'>{String(h.comment)}</div>}
      {perms.includes('mes.exec:hold') && (
        <Button
          size='sm'
          variant='outline'
          className='mt-1'
          data-testid='open-release'
          onClick={() => setOpen(true)}
        >
          {t('mes.exec.release')}
        </Button>
      )}
      <ReleaseDialog
        hold={h}
        reasons={cx.reasons.release}
        open={open}
        onOpenChange={setOpen}
      />
    </div>
  )
}

function HoldDialog({
  cx,
  open,
  onOpenChange,
}: {
  cx: ExecContext
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const qc = useQueryClient()
  const { entity } = useMesEntity('lot_hold')
  const [reason, setReason] = useState('')
  const [comment, setComment] = useState('')
  const m = useMutation({
    mutationFn: () =>
      execApi.hold(String(cx.lot.id), reason, comment || undefined),
    onSuccess: () => {
      toast.success(t('mes.exec.held'))
      onOpenChange(false)
      qc.invalidateQueries({ queryKey: ['mes'] })
    },
    onError: (e) => toast.error(mesErrorMessage(e, entity)),
  })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t('mes.exec.hold')} · {String(cx.lot.code)}
          </DialogTitle>
        </DialogHeader>
        <Pick
          id='hold-reason'
          label={t('mes.exec.reason')}
          required
          none={false}
          value={reason}
          onChange={setReason}
          options={cx.reasons.hold.map((r) => ({
            id: r.id,
            label: optLabel(r),
          }))}
        />
        <div className='grid gap-1'>
          <Label htmlFor='hold-comment'>{t('mes.exec.comment')}</Label>
          <Textarea
            id='hold-comment'
            rows={2}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button disabled={!reason || m.isPending} onClick={() => m.mutate()}>
            {t('mes.exec.hold')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** 释放 Hold 对话框（选择原因代码并填写备注）。 */
export function ReleaseDialog({
  hold,
  reasons,
  open,
  onOpenChange,
}: {
  hold: Record<string, unknown>
  reasons: { id: string; code: string; name?: string }[]
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  const qc = useQueryClient()
  const { entity } = useMesEntity('lot_hold')
  const [reason, setReason] = useState('')
  const [comment, setComment] = useState('')
  const m = useMutation({
    mutationFn: () =>
      execApi.release(String(hold.id), reason || null, comment || undefined),
    onSuccess: () => {
      toast.success(t('mes.exec.released'))
      onOpenChange(false)
      qc.invalidateQueries({ queryKey: ['mes'] })
    },
    onError: (e) => toast.error(mesErrorMessage(e, entity)),
  })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {t('mes.exec.release')} · {String(hold.lot_label ?? '')}
          </DialogTitle>
          <DialogDescription>
            {String(hold.reason_label ?? '')}
          </DialogDescription>
        </DialogHeader>
        <Pick
          id='release-reason'
          label={t('mes.exec.releaseReason')}
          value={reason}
          onChange={setReason}
          options={reasons.map((r) => ({ id: r.id, label: optLabel(r) }))}
        />
        <div className='grid gap-1'>
          <Label htmlFor='release-comment'>{t('mes.exec.comment')}</Label>
          <Textarea
            id='release-comment'
            rows={2}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button disabled={m.isPending} onClick={() => m.mutate()}>
            {t('mes.exec.release')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
