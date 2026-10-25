/** Hold 卡片：当前 Hold 列表、Hold 按钮与逐条释放。 */
import { useState } from 'react'
import { fmtDateTime, t } from '@/i18n'
import { CircleCheck, PauseCircle } from 'lucide-react'
import type { ExecContext } from '@/lib/api/mes/execution'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState } from '@/components/desc-list'
import {
  enumLabel,
  holdSourceLabel,
  reasonLabel,
} from '@/features/mes/common/labels'
import { MES_PERM, useMesCan } from '@/features/mes/common/mes-perm'
import type { QtimeHoldFields, StepNames } from '../hold/qtime-hold'
import { QtimeHoldInfo } from '../hold/qtime-hold-info'
import { canHold } from '../shared/lot-rules'
import { SideCardHeader } from '../shared/side-card-header'
import { HoldDialog } from './hold-dialog'
import { ReleaseDialog } from './release-dialog'

export function HoldCard({ cx }: { cx: ExecContext }) {
  const can = useMesCan()
  const [holdOpen, setHoldOpen] = useState(false)
  return (
    <>
      <Card className='gap-3'>
        <SideCardHeader icon={PauseCircle} title={t('menu.mes-lot_hold')}>
          {can(MES_PERM.execHold) && canHold(cx.lot) && (
            <Button
              size='sm'
              variant='outline'
              data-testid='open-hold'
              onClick={() => setHoldOpen(true)}
            >
              {t('mes.exec.hold')}
            </Button>
          )}
        </SideCardHeader>
        <CardContent className='space-y-2 text-sm'>
          {cx.holds.length === 0 && (
            <EmptyState icon={CircleCheck}>{t('mes.exec.noHolds')}</EmptyState>
          )}
          {cx.holds.map((h) => (
            <HoldRow key={String(h.id)} h={h} cx={cx} />
          ))}
        </CardContent>
      </Card>
      <HoldDialog cx={cx} open={holdOpen} onOpenChange={setHoldOpen} />
    </>
  )
}

function HoldRow({
  h,
  cx,
}: {
  h: ExecContext['holds'][number]
  cx: ExecContext
}) {
  const can = useMesCan()
  const [open, setOpen] = useState(false)
  return (
    <div className='rounded-md border p-2'>
      <div className='flex items-center justify-between gap-2'>
        <span className='font-medium'>{reasonLabel(h.reason_label)}</span>
        <Badge variant='outline'>
          {enumLabel('hold_type', String(h.hold_type))}
        </Badge>
      </div>
      <div className='text-xs text-muted-foreground'>
        {fmtDateTime(String(h.held_at))} · {String(h.held_by ?? '')} ·{' '}
        {holdSourceLabel(h.source)}
      </div>
      {!!h.comment && <div className='text-xs'>{String(h.comment)}</div>}
      <QtimeHoldInfo hold={h as QtimeHoldFields} steps={stepNames(cx)} />
      {can(MES_PERM.execHold) && (
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

/** 当前流程工步 id -> “序号 · 工序” 显示名（用于 Q-Time Hold 的起止工步）。 */
function stepNames(cx: ExecContext): StepNames {
  return Object.fromEntries(
    (cx.route_steps ?? []).map((s) => [
      s.id,
      s.operation ? `${s.seq} · ${s.operation}` : String(s.seq),
    ])
  )
}
