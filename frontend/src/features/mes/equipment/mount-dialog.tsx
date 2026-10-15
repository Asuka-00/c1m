/** 机台上料对话框（F2）：当前各上料口在装的料、卸料、人工上料。 */
import { useState } from 'react'
import { AxiosError } from 'axios'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi } from '@/lib/api/mes/common'
import { mountApi, type MountRow } from '@/lib/api/mes/equipment'
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
import { newEventId } from '@/features/mes/common/event-id'
import { MES_PERM, useMesCan } from '@/features/mes/common/mes-perm'
import { mesErrorMessage } from '@/features/mes/common/required'
import { Pick } from '@/features/mes/execution/exec-parts'

/** 409 业务错误的 detail。 */
function conflict(e: unknown): Record<string, unknown> | null {
  if (!(e instanceof AxiosError) || e.response?.status !== 409) return null
  const d = (e.response.data as { detail?: unknown })?.detail
  return d && typeof d === 'object' ? (d as Record<string, unknown>) : null
}

/** 上料 / 卸料的错误提示。 */
export function mountErrorMessage(e: unknown): string {
  const d = conflict(e)
  if (d?.code === 'port_occupied')
    return d.current_material_lot_code
      ? t('mes.mount.portOccupied', {
          port: d.port_code,
          lot: d.current_material_lot_code,
        })
      : t('mes.mount.portBusy')
  if (d?.code === 'mount_overlap') return t('mes.mount.overlap')
  if (d?.code === 'already_unmounted') return t('mes.mount.alreadyUnmounted')
  return mesErrorMessage(e, undefined)
}

/** 卸料按钮（对话框和通用上料记录列表共用）。 */
export function UnmountButton({ row }: { row: MountRow }) {
  const can = useMesCan()
  const qc = useQueryClient()
  const m = useMutation({
    mutationFn: () => mountApi.unmount(row.id),
    onSuccess: () => toast.success(t('mes.mount.unmounted')),
    onError: (e) => toast.error(mountErrorMessage(e)),
    onSettled: () => qc.invalidateQueries({ queryKey: ['mes'] }),
  })
  if (row.unmounted_at) return null
  return (
    <Button
      size='sm'
      variant='outline'
      disabled={!can(MES_PERM.equipmentMount) || m.isPending}
      onClick={() => m.mutate()}
    >
      {t('mes.mount.unmount')}
    </Button>
  )
}

/** 机台上料对话框。 */
export function MountDialog({
  eq,
  onClose,
}: {
  eq: { id: string; code: string }
  onClose: () => void
}) {
  const tk = useTenantKey()
  const qc = useQueryClient()
  const can = useMesCan()
  const [port, setPort] = useState('')
  const [lot, setLot] = useState('')
  const [comment, setComment] = useState('')
  // 每次打开表单生成一个事件号；重复提交按后端幂等返回处理（D30）
  const [eventId, setEventId] = useState(newEventId)
  const current = useQuery({
    queryKey: ['mes', 'eqp', tk, 'mount-at', eq.id],
    queryFn: () => mountApi.at(eq.id, new Date().toISOString()),
  })
  const ports = useQuery({
    queryKey: ['mes', 'equipment', tk, 'load-ports', eq.id],
    queryFn: () =>
      mesApi.list('equipment', {
        parent_id: eq.id,
        unit_kind: 'load_port',
        page_size: 100,
      }),
  })
  const portOpts = (ports.data?.data ?? []).map((p) => ({
    id: String(p.code),
    label: String(p.code),
  }))
  const m = useMutation({
    mutationFn: () =>
      mountApi.mount(eq.id, {
        port_code: port.trim(),
        material_lot_code: lot.trim(),
        external_event_id: eventId,
        comment: comment.trim() || undefined,
      }),
    onSuccess: (res) => {
      toast.success(
        res?.duplicate
          ? t('mes.mount.duplicate', {
              port: res.data.port_code,
              lot: res.data.material_lot_code ?? res.data.material_lot_id,
            })
          : t('mes.mount.mounted')
      )
      setLot('')
      setComment('')
      setEventId(newEventId())
    },
    onError: (e) => toast.error(mountErrorMessage(e)),
    onSettled: () => qc.invalidateQueries({ queryKey: ['mes'] }),
  })
  const rows = current.data ?? []
  const allowed = can(MES_PERM.equipmentMount)
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-xl'>
        <DialogHeader>
          <DialogTitle>
            {t('mes.mount.title')} · {eq.code}
          </DialogTitle>
          <DialogDescription>{t('mes.mount.desc')}</DialogDescription>
        </DialogHeader>
        <div className='grid gap-2' data-testid='mount-current'>
          <div className='text-sm font-medium'>{t('mes.mount.current')}</div>
          {rows.length === 0 ? (
            <div className='text-sm text-muted-foreground'>
              {current.isLoading ? '…' : t('mes.mount.empty')}
            </div>
          ) : (
            rows.map((r) => (
              <div
                key={r.id}
                className='flex items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm'
              >
                <span>
                  <span className='font-mono'>{r.port_code}</span>
                  {' · '}
                  <span className='font-mono'>
                    {r.material_lot_code ?? '—'}
                  </span>
                  <span className='ms-2 text-xs text-muted-foreground'>
                    {fmtDateTime(r.mounted_at)}
                  </span>
                </span>
                <UnmountButton row={r} />
              </div>
            ))
          )}
        </div>
        <div className='grid gap-3 border-t pt-3'>
          {portOpts.length > 0 ? (
            <Pick
              id='mount-port'
              label={t('mes.mount.port')}
              required
              none={false}
              value={port}
              onChange={(v) => {
                setPort(v)
                setEventId(newEventId())
              }}
              options={portOpts}
            />
          ) : (
            <div className='grid gap-1'>
              <Label htmlFor='mount-port'>
                {t('mes.mount.port')}
                <span className='text-destructive'> *</span>
              </Label>
              <Input
                id='mount-port'
                maxLength={64}
                value={port}
                onChange={(e) => {
                  setPort(e.target.value)
                  setEventId(newEventId())
                }}
              />
            </div>
          )}
          <div className='grid gap-1'>
            <Label htmlFor='mount-lot'>
              {t('mes.mount.lot')}
              <span className='text-destructive'> *</span>
            </Label>
            <Input
              id='mount-lot'
              maxLength={64}
              value={lot}
              onChange={(e) => {
                setLot(e.target.value)
                setEventId(newEventId())
              }}
            />
          </div>
          <div className='grid gap-1'>
            <Label htmlFor='mount-comment'>{t('mes.exec.comment')}</Label>
            <Textarea
              id='mount-comment'
              rows={2}
              maxLength={300}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            disabled={!allowed || !port.trim() || !lot.trim() || m.isPending}
            onClick={() => m.mutate()}
          >
            {t('mes.mount.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
