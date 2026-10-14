/** 光罩管理页面（P3）：列表 + 详情（状态履历 / 计数 / 挂载 / 检查）+ 动作按钮。 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { toast } from 'sonner'
import {
  RETICLE_MOCK,
  RETICLE_STATUSES,
  reticleApi,
  type Reticle,
  type ReticleAction,
} from '@/lib/api/mes/reticle'
import { decimalText } from '@/lib/decimal'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Page } from '@/components/crud'
import { useOperationKey } from '@/features/mes/common/idem-key'
import { MES_PERM, useMesCan } from '@/features/mes/common/mes-perm'
import { ReticleActionDialog } from './action-dialog'
import { ReticleLifeBar } from './life-bar'
import { ReticleMasterDialog } from './master-dialog'
import {
  actionEnabled,
  actionHint,
  inspectionPending,
  actionLabel,
  disabledHint,
  reticleErrorMessage,
  visibleActions,
} from './reticle-rules'

const dash = (v: unknown) => (v == null || v === '' ? '—' : String(v))
/** 计数（定点字符串，兼容数字）；空为 —。 */
const numDash = (v: number | string | null | undefined) =>
  v == null || v === '' ? '—' : decimalText(v)
const statusText = (s: string | null) =>
  s ? t(`mes.reticle.status.${s}`) : '—'
const holdText = (s: string | null) =>
  s ? t(`mes.reticle.holdReason.${s}`) : '—'

/** 状态徽标。 */
export function StatusBadge({ status }: { status: string }) {
  const tone =
    status === 'available'
      ? 'default'
      : status === 'scrapped'
        ? 'outline'
        : status === 'on_hold' || status === 'pending_maintenance'
          ? 'destructive'
          : 'secondary'
  return (
    <Badge variant={tone} data-testid={`status-${status}`}>
      {statusText(status)}
    </Badge>
  )
}

function Grid({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <dl className='grid grid-cols-2 gap-x-4 gap-y-1 text-sm md:grid-cols-4'>
      {rows.map(([k, v]) => (
        <div key={k} className='contents'>
          <dt className='text-muted-foreground'>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  )
}

function Simple({
  cols,
  rows,
  testId,
}: {
  cols: string[]
  rows: React.ReactNode[][]
  testId: string
}) {
  return (
    <Table data-testid={testId}>
      <TableHeader>
        <TableRow>
          {cols.map((c) => (
            <TableHead key={c}>{t(`mes.reticle.col.${c}`)}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.length === 0 ? (
          <TableRow>
            <TableCell colSpan={cols.length} className='text-muted-foreground'>
              {t('mes.reticle.emptyHint')}
            </TableCell>
          </TableRow>
        ) : (
          rows.map((r, i) => (
            <TableRow key={i}>
              {r.map((c, j) => (
                <TableCell key={j}>{c}</TableCell>
              ))}
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  )
}

/** 光罩详情（基本信息 + 动作 + 四个记录页签）。 */
export function ReticleDetail({ reticle }: { reticle: Reticle }) {
  const can = useMesCan()
  const [action, setAction] = useState<ReticleAction | null>(null)
  const h = useQuery({
    queryKey: ['mes', 'reticle', 'history', reticle.id],
    queryFn: () => reticleApi.history(reticle.id),
  })
  const [edit, setEdit] = useState(false)
  const acts = visibleActions(can)
  const qc = useQueryClient()
  const delKey = useOperationKey()
  const del = useMutation({
    mutationFn: () =>
      reticleApi.remove(reticle.id, delKey.key(`remove:${reticle.id}`)),
    onSuccess: () => {
      delKey.done()
      qc.invalidateQueries({ queryKey: ['mes', 'reticle'] })
    },
    // D72：有履历 → 409 referenced
    onError: (e) => toast.error(reticleErrorMessage(e)),
  })
  const hint = disabledHint(reticle)
  return (
    <div className='flex flex-col gap-3 rounded-md border p-4'>
      <div className='flex flex-wrap items-center gap-2'>
        <h3 className='text-lg font-semibold'>{reticle.code}</h3>
        <StatusBadge status={reticle.status_code} />
        {inspectionPending(reticle) && (
          <Badge variant='secondary'>
            {t('mes.reticle.inspectionPending')}
          </Badge>
        )}
      </div>
      <Grid
        rows={[
          [t('mes.reticle.field.revision'), dash(reticle.revision)],
          [t('mes.reticle.field.layer'), dash(reticle.layer)],
          [t('mes.reticle.field.hold_reason'), holdText(reticle.hold_reason)],
          [
            t('mes.reticle.field.status_before_hold'),
            statusText(reticle.status_before_hold),
          ],
          [
            t('mes.reticle.field.shots'),
            <ReticleLifeBar key='s' reticle={reticle} />,
          ],
          [t('mes.reticle.field.mount_count'), reticle.mount_count],
          [t('mes.reticle.field.life_reset_count'), reticle.life_reset_count],
          [
            t('mes.reticle.field.count_basis'),
            t(`mes.reticle.countBasis.${reticle.count_basis}`),
          ],
          [t('mes.reticle.field.equipment'), dash(reticle.equipment_label)],
          [t('mes.reticle.field.mounted_at'), fmtDateTime(reticle.mounted_at)],
          [
            t('mes.reticle.field.storage_location'),
            dash(reticle.storage_location),
          ],
          [
            t('mes.reticle.field.next_inspection_due_at'),
            fmtDateTime(reticle.next_inspection_due_at),
          ],
        ]}
      />
      {acts.length > 0 && (
        <div className='flex flex-wrap gap-2' data-testid='reticle-actions'>
          {acts.map((a) => (
            <Button
              key={a}
              size='sm'
              variant={a === 'scrap' ? 'destructive' : 'outline'}
              disabled={!actionEnabled(reticle, a)}
              title={actionHint(reticle, a) || t(`mes.reticle.actionDesc.${a}`)}
              onClick={() => setAction(a)}
              data-testid={`reticle-act-${a}`}
            >
              {t(`mes.reticle.action.${a}`)}
            </Button>
          ))}
          {can(MES_PERM.reticleWrite) && (
            <Button
              size='sm'
              variant='outline'
              title={t('mes.reticle.master.editTip')}
              onClick={() => setEdit(true)}
              data-testid='reticle-edit'
            >
              {t('mes.reticle.master.edit')}
            </Button>
          )}
          {/* 删除走通用 CRUD 的 write 权限（不是 override） */}
          {can(MES_PERM.reticleWrite) && (
            <Button
              size='sm'
              variant='destructive'
              disabled={del.isPending}
              onClick={() => {
                if (
                  window.confirm(
                    t('mes.reticle.deleteConfirm', { code: reticle.code })
                  )
                )
                  del.mutate()
              }}
              title={t('mes.reticle.deleteTip')}
              data-testid='reticle-delete'
            >
              {t('mes.reticle.delete')}
            </Button>
          )}
        </div>
      )}
      {hint && (
        <p className='text-sm text-muted-foreground' data-testid='reticle-hint'>
          {hint}
        </p>
      )}
      <Tabs defaultValue='status'>
        <TabsList>
          <TabsTrigger value='status'>
            {t('mes.reticle.tab.status')}
          </TabsTrigger>
          <TabsTrigger value='usage'>{t('mes.reticle.tab.usage')}</TabsTrigger>
          <TabsTrigger value='mounts'>
            {t('mes.reticle.tab.mounts')}
          </TabsTrigger>
          <TabsTrigger value='inspections'>
            {t('mes.reticle.tab.inspections')}
          </TabsTrigger>
        </TabsList>
        <TabsContent value='status'>
          <Simple
            testId='reticle-status-log'
            cols={[
              'at',
              'from',
              'to',
              'action',
              'holdReason',
              'reason',
              'comment',
              'user',
            ]}
            rows={(h.data?.status_log ?? []).map((x) => [
              fmtDateTime(x.at),
              statusText(x.from_status),
              statusText(x.to_status),
              actionLabel(x.action),
              holdText(x.hold_reason_to),
              dash(x.reason),
              dash(x.comment),
              dash(x.username),
            ])}
          />
        </TabsContent>
        <TabsContent value='usage'>
          <Simple
            testId='reticle-usage-log'
            cols={[
              'at',
              'kind',
              'delta',
              'countAfter',
              'lot',
              'reasonId',
              'comment',
              'user',
            ]}
            rows={(h.data?.usage ?? []).map((x) => [
              fmtDateTime(x.occurred_at),
              t(`mes.reticle.usageKind.${x.kind}`),
              x.delta,
              x.counted
                ? decimalText(x.count_after)
                : `${decimalText(x.count_after)} (${t('mes.reticle.notCounted')})`,
              dash(x.lot_label ?? x.lot_id),
              dash(x.reason_label ?? x.reason_id),
              dash(x.comment),
              dash(x.username),
            ])}
          />
        </TabsContent>
        <TabsContent value='mounts'>
          <Simple
            testId='reticle-mount-log'
            cols={[
              'equipment',
              'slot',
              'mountedAt',
              'unmountedAt',
              'unmountReason',
              'shotsAtMount',
              'shotsAtUnmount',
            ]}
            rows={(h.data?.mounts ?? []).map((x) => [
              dash(x.equipment_label ?? x.equipment_id),
              dash(x.slot_code),
              fmtDateTime(x.mounted_at),
              x.unmounted_at
                ? fmtDateTime(x.unmounted_at)
                : t('mes.reticle.mounted'),
              dash(x.unmount_reason),
              decimalText(x.shots_at_mount),
              numDash(x.shots_at_unmount),
            ])}
          />
        </TabsContent>
        <TabsContent value='inspections'>
          <Simple
            testId='reticle-inspection-log'
            cols={[
              'at',
              'inspKind',
              'result',
              'defects',
              'disposition',
              'comment',
              'user',
            ]}
            rows={(h.data?.inspections ?? []).map((x) => [
              fmtDateTime(x.inspected_at),
              t(`mes.reticle.inspKind.${x.kind}`),
              t(`mes.reticle.result.${x.result}`),
              dash(x.defect_count),
              t(`mes.reticle.disposition.${x.disposition}`),
              dash(x.comment),
              dash(x.username),
            ])}
          />
        </TabsContent>
      </Tabs>
      <ReticleActionDialog
        reticle={reticle}
        action={action}
        onClose={() => setAction(null)}
      />
      <ReticleMasterDialog
        reticle={reticle}
        open={edit}
        onClose={() => setEdit(false)}
      />
    </div>
  )
}

/** 光罩列表页（菜单组件 key `mes-page:reticle`）。 */
export default function ReticlePage() {
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [sel, setSel] = useState<string | null>(null)
  const list = useQuery({
    queryKey: ['mes', 'reticle', 'list'],
    queryFn: reticleApi.list,
  })
  const rows = (list.data ?? []).filter(
    (r) =>
      (!status || r.status_code === status) &&
      (!q || r.code.toLowerCase().includes(q.toLowerCase()))
  )
  const cur = list.data?.find((r) => r.id === sel)
  const can = useMesCan()
  const [creating, setCreating] = useState(false)
  return (
    <Page
      title={t('mes.reticle.title')}
      description={
        RETICLE_MOCK ? t('mes.reticle.mockHint') : t('mes.reticle.desc')
      }
    >
      <div className='flex flex-wrap gap-2'>
        <Input
          className='w-56'
          placeholder={t('mes.reticle.searchCode')}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          data-testid='reticle-search'
        />
        <select
          className='rounded-md border border-input bg-transparent px-2 text-sm'
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          aria-label={t('mes.reticle.field.status')}
          data-testid='reticle-status-filter'
          title={t('mes.reticle.statusFilterTip')}
        >
          <option value=''>{t('mes.reticle.allStatus')}</option>
          {RETICLE_STATUSES.map((s) => (
            <option key={s} value={s}>
              {statusText(s)}
            </option>
          ))}
        </select>
      </div>
      {can(MES_PERM.reticleWrite) && (
        <Button
          size='sm'
          className='self-start'
          title={t('mes.reticle.master.createTip')}
          onClick={() => setCreating(true)}
          data-testid='reticle-create'
        >
          {t('mes.reticle.master.create')}
        </Button>
      )}
      <ReticleMasterDialog
        reticle={null}
        open={creating}
        onClose={() => setCreating(false)}
      />
      <Table data-testid='reticle-list'>
        <TableHeader>
          <TableRow>
            {['code', 'status', 'layer', 'shots', 'equipment', 'location'].map(
              (c) => (
                <TableHead key={c} title={t(`mes.reticle.colTip.${c}`)}>
                  {t(`mes.reticle.col.${c}`)}
                </TableHead>
              )
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow
              key={r.id}
              onClick={() => setSel(r.id)}
              className={cn('cursor-pointer', r.id === sel && 'bg-muted')}
              data-testid={`reticle-row-${r.code}`}
            >
              <TableCell>{r.code}</TableCell>
              <TableCell>
                <StatusBadge status={r.status_code} />
              </TableCell>
              <TableCell>{dash(r.layer)}</TableCell>
              <TableCell>
                <ReticleLifeBar reticle={r} />
              </TableCell>
              <TableCell>{dash(r.equipment_label)}</TableCell>
              <TableCell>{dash(r.storage_location)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {cur && <ReticleDetail reticle={cur} />}
    </Page>
  )
}
