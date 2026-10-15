/** 批次概要卡片：编号与状态徽标、关键信息、阶段步骤条、子流程与 Q-Time 提示。 */
import { fmtDateTime, t } from '@/i18n'
import { Info, PauseCircle, Timer } from 'lucide-react'
import type { ExecContext } from '@/lib/api/mes/execution'
import { splitLabel } from '@/lib/split-label'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { DescItem, DescList } from '@/components/desc-list'
import { enumLabel, optLabel } from '@/features/mes/common/labels'
import { StageBar } from '../exec-parts'

export function LotSummaryCard({ cx }: { cx: ExecContext }) {
  const lot = cx.lot
  const stage = cx.next_stage
  const step = cx.step
  const onHold = !!lot.on_hold
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
                kind: t(`mes.exec.frame.${cx.stack[cx.stack.length - 1].kind}`),
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
  )
}
