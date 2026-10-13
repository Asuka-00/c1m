/** Hold 卡片：当前 Hold 列表、Hold 按钮与逐条释放。 */
import { useState } from 'react'
import { fmtDateTime, t } from '@/i18n'
import { CircleCheck, PauseCircle } from 'lucide-react'
import type { ExecContext } from '@/lib/api/mes/execution'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { EmptyState } from '@/components/desc-list'
import { enumLabel } from '@/features/mes/common/labels'
import { HoldDialog } from './hold-dialog'
import { ReleaseDialog } from './release-dialog'

export function HoldCard({ cx, perms }: { cx: ExecContext; perms: string[] }) {
  const terminal = !cx.next_stage
  const [holdOpen, setHoldOpen] = useState(false)
  return (
    <>
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
            <EmptyState icon={CircleCheck}>{t('mes.exec.noHolds')}</EmptyState>
          )}
          {cx.holds.map((h) => (
            <HoldRow key={String(h.id)} h={h} cx={cx} perms={perms} />
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
