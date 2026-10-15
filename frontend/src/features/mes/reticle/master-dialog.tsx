/** 光罩主数据新建 / 编辑（P3-F3）。状态、计数、挂载只读，走动作接口。 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { toast } from 'sonner'
import {
  RETICLE_MASTER_FIELDS,
  reticleApi,
  type Reticle,
} from '@/lib/api/mes/reticle'
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
import { useOperationKey } from '@/features/mes/common/idem-key'
import { init, masterBody, masterErrors, type F, type V } from './master-form'
import { reticleErrorMessage } from './reticle-rules'

export function ReticleMasterDialog({
  reticle,
  open,
  onClose,
}: {
  reticle: Reticle | null
  open: boolean
  onClose: () => void
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      {open && <Body reticle={reticle} onClose={onClose} />}
    </Dialog>
  )
}

function Body({
  reticle: r,
  onClose,
}: {
  reticle: Reticle | null
  onClose: () => void
}) {
  const [v, setV] = useState<V>(() => init(r))
  const [tried, setTried] = useState(false)
  const qc = useQueryClient()
  const errs = masterErrors(v)
  const opKey = useOperationKey()
  const m = useMutation({
    mutationFn: () => {
      const body = masterBody(v, r)
      const sig = `${r?.id ?? 'new'}:${JSON.stringify(body)}`
      return reticleApi.save(r?.id ?? null, body, opKey.key(sig))
    },
    onSuccess: () => {
      opKey.done()
      toast.success(t('mes.saved'))
      qc.invalidateQueries({ queryKey: ['mes', 'reticle'] })
      onClose()
    },
    onError: (e) => toast.error(reticleErrorMessage(e)),
  })
  const field = (k: F) => (
    <div key={k} className='flex flex-col gap-1'>
      <Label htmlFor={`rm-${k}`} title={t(`mes.reticle.master.tip.${k}`)}>
        {t(`mes.reticle.master.field.${k}`)}
        {k === 'code' && ' *'}
      </Label>
      {k === 'count_basis' ? (
        <select
          id={`rm-${k}`}
          className='h-9 rounded-md border border-input bg-transparent px-2 text-sm'
          value={v[k]}
          title={t(`mes.reticle.master.tip.${k}`)}
          onChange={(e) => setV({ ...v, [k]: e.target.value })}
        >
          {['track_out', 'eap'].map((b) => (
            <option key={b} value={b}>
              {t(`mes.reticle.countBasis.${b}`)}
            </option>
          ))}
        </select>
      ) : (
        <Input
          id={`rm-${k}`}
          value={v[k]}
          disabled={k === 'code' && r != null}
          inputMode={
            k === 'max_shots' || k === 'warn_ratio' ? 'decimal' : undefined
          }
          title={t(`mes.reticle.master.tip.${k}`)}
          onChange={(e) => setV({ ...v, [k]: e.target.value })}
        />
      )}
      {tried && errs[k] && (
        <p className='text-sm text-destructive' role='alert'>
          {errs[k]}
        </p>
      )}
    </div>
  )
  return (
    <DialogContent className='sm:max-w-xl' data-testid='reticle-master-dialog'>
      <DialogHeader>
        <DialogTitle>
          {r
            ? t('mes.reticle.master.editTitle', { code: r.code })
            : t('mes.reticle.master.createTitle')}
        </DialogTitle>
        <DialogDescription>{t('mes.reticle.master.desc')}</DialogDescription>
      </DialogHeader>
      <div className='grid grid-cols-2 gap-3'>
        {RETICLE_MASTER_FIELDS.map(field)}
      </div>
      <DialogFooter>
        <Button variant='outline' onClick={onClose}>
          {t('common.cancel')}
        </Button>
        <Button
          disabled={m.isPending}
          onClick={() => {
            setTried(true)
            if (Object.keys(errs).length === 0) m.mutate()
          }}
          data-testid='reticle-master-save'
        >
          {t('common.save')}
        </Button>
      </DialogFooter>
    </DialogContent>
  )
}
