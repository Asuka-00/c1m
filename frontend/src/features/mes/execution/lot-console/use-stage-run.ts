/** 阶段作业的执行与预检：调用后端、提示结果并维护检查结果面板状态。 */
import { useState } from 'react'
import { AxiosError } from 'axios'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import i18n, { t } from '@/i18n'
import { toast } from 'sonner'
import {
  blockedResults,
  execApi,
  type CheckResult,
  type ExecContext,
  type ExecStage,
  type StageBody,
} from '@/lib/api/mes/execution'
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesEntity } from '@/features/mes/common/use-mes-meta'

const detailOf = (e: unknown) =>
  e instanceof AxiosError
    ? ((e.response?.data as { detail?: unknown })?.detail as
        | { code?: string; message?: string }
        | undefined)
    : undefined

/** 后端因 Q-Time 超时把批次转 Hold 后拒绝本次作业（422 on_hold，message 含 Q-Time）。 */
export function isQtimeHoldError(e: unknown) {
  const d = detailOf(e)
  return (
    !!d &&
    typeof d === 'object' &&
    d.code === 'on_hold' &&
    /q-?time/i.test(String(d.message ?? ''))
  )
}

const isLotStateError = (e: unknown) => {
  const c = detailOf(e)?.code
  return c === 'on_hold' || c === 'lot_status' || c === 'lot_busy'
}

/** Q-Time 超时处置提示：处置结果 + 本次作业未执行。 */
export function qtimeNotice(action: string, stage: string | null) {
  const key = `mes.exec.qtimeAction.${action}`
  return [
    i18n.exists(key) ? t(key) : t('mes.exec.qtimeHandled'),
    stage &&
      t('mes.exec.qtimeStageSkipped', { stage: t(`mes.exec.stage.${stage}`) }),
  ]
    .filter(Boolean)
    .join(' · ')
}

/**
 * 阶段作业的执行（run，可带强制放行原因）与预检（preview）。
 *
 * @param cx 批次执行上下文
 * @param body 返回当前请求体的函数
 * @returns run / preview 两个 mutation，以及检查结果与是否被卡控
 */
export function useStageRun(cx: ExecContext, body: () => StageBody) {
  const qc = useQueryClient()
  const { entity: lotE } = useMesEntity('lot')
  const lot = cx.lot
  const stage = cx.next_stage
  const [results, setResults] = useState<CheckResult[] | null>(null)
  const [blocked, setBlocked] = useState(false)
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
      if (r.future_hold?.length) {
        toast.warning(
          t('mes.exec.futureHold', {
            reason: r.future_hold.map((x) => x.comment || x.reason).join('; '),
          })
        )
        qc.invalidateQueries({ queryKey: ['mes'] })
        return
      }
      if (r.qtime) {
        // Q-Time 超时处置（Move In 停表点，D19 后为 Track In）：后端 200 返回 qtime，本次作业未执行
        toast.warning(qtimeNotice(r.qtime, stage))
        qc.invalidateQueries({ queryKey: ['mes'] })
        return
      }
      const auto = (r.auto ?? []).filter((a) => a.ok).map((a) => a.stage)
      toast.success(
        [
          t(`mes.exec.done.${stage}`),
          ...auto.map((s) =>
            t('mes.exec.autoDone', { stage: t(`mes.exec.stage.${s}`) })
          ),
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
        return
      }
      if (isQtimeHoldError(e)) {
        // 兼容：D22 前的后端在 Track In 超时转 Hold 后返回 422 on_hold（message 含 Q-Time）；
        // D22 起改为 200 + qtime（见 onSuccess），后端落地后可删除此分支
        toast.warning(qtimeNotice('hold', stage))
        qc.invalidateQueries({ queryKey: ['mes'] })
        return
      }
      toast.error(mesErrorMessage(e, lotE))
      // 状态类错误说明批次已被其他操作改变，刷新以显示最新状态
      if (isLotStateError(e)) qc.invalidateQueries({ queryKey: ['mes'] })
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
  return { run, preview, results, blocked }
}

export type StageRun = ReturnType<typeof useStageRun>
