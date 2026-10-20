/** 作业面板：当前阶段的输入、预检与执行按钮；终态批次显示完成提示。 */
import { t } from '@/i18n'
import {
  CircleCheck,
  Loader2,
  PauseCircle,
  PlayCircle,
  SearchCheck,
} from 'lucide-react'
import type { ExecContext } from '@/lib/api/mes/execution'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { enumLabel, optLabel } from '@/features/mes/common/labels'
import { ChamberPick } from '../shared/chamber-pick'
import { Pick } from '../shared/exec-parts'
import { TrackInInputs } from './track-in-inputs'
import { TrackOutInputs } from './track-out-inputs'
import type { StageForm } from './use-stage-form'
import type { StageRun } from './use-stage-run'

export function ActionPanel({
  cx,
  form,
  stageRun,
  canRun,
}: {
  cx: ExecContext
  form: StageForm
  stageRun: StageRun
  canRun: boolean
}) {
  const lot = cx.lot
  const stage = cx.next_stage
  const step = cx.step
  const terminal = !stage
  const onHold = !!lot.on_hold
  const { run, preview } = stageRun
  const {
    qty,
    activeUnits,
    eqChambers,
    equipment,
    setEquipment,
    recipe,
    setRecipe,
    chambers,
    setChambers,
    eqpRecipe,
    setEqpRecipe,
    reticle,
    setReticle,
    carrier,
    setCarrier,
    tools,
    setTools,
    mats,
    setMats,
    dc,
    setDc,
    scrap,
    setScrap,
    rework,
    setRework,
    branch,
    setBranch,
    doRework,
    setDoRework,
  } = form
  return !terminal ? (
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
            <AlertDescription>{t('mes.exec.holdBlocks')}</AlertDescription>
          </Alert>
        )}
        {(stage === 'move_in' || stage === 'track_in') && (
          <div className='grid gap-4 sm:grid-cols-2'>
            <Pick
              id='ex-eqp'
              label={t('mes.exec.equipment')}
              required={stage === 'track_in' && (cx.equipment?.length ?? 0) > 0}
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
            {stage === 'track_in' && (
              <ChamberPick
                options={eqChambers}
                value={chambers}
                onChange={setChambers}
              />
            )}
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
  )
}
