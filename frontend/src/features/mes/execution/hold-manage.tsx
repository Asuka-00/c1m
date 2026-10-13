/**
 * Hold 管理页面（合并原「批量释放 Hold」）：默认显示生效中的 Hold，可切换历史（已解除）/ 全部；
 * 按原因 / 来源 / 产品 / Hold 时间筛选；支持单条释放与勾选后批量释放（须释放原因代码）。
 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { Download, PlayCircle, Unlock } from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi } from '@/lib/api/mes/common'
import { execApi, type HoldRow } from '@/lib/api/mes/execution'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import {
  DataTable,
  Page,
  downloadCsv,
  searchFilter,
  useListParams,
  type FilterDef,
} from '@/components/crud'
import { enumLabel, optLabel } from '@/features/mes/common/labels'
import { MES_PERM, useMesCan } from '@/features/mes/common/mes-perm'
import { RefLink } from '@/features/mes/common/ref-link'
import { mesErrorMessage } from '@/features/mes/common/required'
import { Pick } from './exec-parts'

/** Hold 来源。 */
const SOURCES = ['manual', 'qtime', 'oos', 'split']
/** 状态切换：生效中（默认）/ 已解除（历史）/ 全部。 */
type Status = 'active' | 'released' | 'all'

/** 主数据下拉选项（按编码筛选，与 Hold 行的原因 / 产品编码对应）。 */
const codeOptions =
  (entity: string, f: Record<string, string> = {}) =>
  () =>
    mesApi.list(entity, { ...f, page_size: 100 }).then((r) =>
      r.data.map((x) => ({
        value: String(x.code),
        label: optLabel(x as { code: string; name?: string }),
      }))
    )

/** 来源显示文本。 */
const srcLabel = (s: string) =>
  SOURCES.includes(s) ? t(`mes.holdrel.src.${s}`) : s

/** Hold 管理。 */
export default function HoldManagePage() {
  const tk = useTenantKey()
  const canRelease = useMesCan()(MES_PERM.execHold)
  const [sel, setSel] = useState<string[]>([])
  const [releasing, setReleasing] = useState<string[] | null>(null)
  const [statusSeen, setStatusSeen] = useState<Status>('active')
  const filters: FilterDef[] = [
    searchFilter(t('mes.holdrel.search')),
    {
      type: 'select',
      name: 'status',
      label: t('mes.holdrel.allStatus'),
      defaultValue: 'active',
      options: (['active', 'released'] as const).map((v) => ({
        value: v,
        label: t(`mes.holdrel.status.${v}`),
      })),
    },
    {
      type: 'select',
      name: 'reason',
      label: t('mes.holdrel.allReasons'),
      optionsKey: ['mes', 'reason_code', 'hold-options'],
      loadOptions: codeOptions('reason_code', { reason_type: 'hold' }),
    },
    {
      type: 'select',
      name: 'source',
      label: t('mes.holdrel.allSources'),
      options: SOURCES.map((s) => ({ value: s, label: srcLabel(s) })),
    },
    {
      type: 'select',
      name: 'product',
      label: t('mes.holdrel.allProducts'),
      optionsKey: ['mes', 'product', 'code-options'],
      loadOptions: codeOptions('product'),
    },
    { type: 'daterange', name: 'held_at', label: t('mes.holdrel.heldAt') },
  ]
  const lp = useListParams(filters)
  const status = (lp.filters.status ?? 'all') as Status
  if (status !== statusSeen) {
    // 切换生效中 / 历史时清空勾选
    setStatusSeen(status)
    setSel([])
  }
  // 终态批次的 Hold 默认不显示（P15 A / N6），开关打开时请求 include_terminal=true
  const [showTerminal, setShowTerminal] = useState(false)
  const terminalParam = showTerminal ? { include_terminal: 'true' } : {}
  const q = useQuery({
    queryKey: ['mes', 'exec', tk, 'holds', lp.query, showTerminal],
    queryFn: () =>
      execApi.holds({ status: 'all', ...lp.query, ...terminalParam }),
  })
  const rows = useMemo(() => q.data?.data ?? [], [q.data])
  const total = q.data?.count ?? 0
  /** 已勾选 Hold 的批次号（跨页保留）。 */
  const [selLots, setSelLots] = useState<Record<string, string>>({})
  const activeView = rows.filter((r) => r.is_active)
  const allOn =
    activeView.length > 0 && activeView.every((r) => sel.includes(r.id))
  const toggleAll = () => {
    setSelLots((m) => ({
      ...m,
      ...Object.fromEntries(activeView.map((r) => [r.id, r.lot])),
    }))
    setSel((s) =>
      allOn
        ? s.filter((x) => !activeView.some((r) => r.id === x))
        : [...new Set([...s, ...activeView.map((r) => r.id)])]
    )
  }
  const showRelease = status !== 'active'
  return (
    <Page
      title={t('menu.mes-lot_hold')}
      description={t('mes.holdrel.hint')}
      actions={
        <>
          <Button
            variant='outline'
            disabled={!total}
            onClick={async () => {
              const { data: all } = await execApi.holds({
                status: 'all',
                ...lp.query,
                ...terminalParam,
                page: 1,
                page_size: 5000,
              })
              downloadCsv(
                'lot_hold',
                [
                  t('mes.holdrel.lot'),
                  t('mes.holdrel.product'),
                  t('mes.holdrel.step'),
                  t('mes.holdrel.reason'),
                  t('mes.holdrel.source'),
                  t('mes.holdrel.heldAt'),
                  t('mes.holdrel.heldBy'),
                  t('mes.holdrel.hours'),
                  t('mes.holdrel.comment'),
                  t('mes.holdrel.releasedAt'),
                  t('mes.holdrel.releasedBy'),
                  t('mes.holdrel.releaseReason'),
                  t('mes.holdrel.releaseComment'),
                ],
                all.map((r) => [
                  r.lot,
                  r.product,
                  r.step_seq,
                  r.reason,
                  srcLabel(r.source),
                  r.held_at && fmtDateTime(r.held_at),
                  r.held_by,
                  r.hours,
                  r.comment,
                  r.released_at && fmtDateTime(r.released_at),
                  r.released_by,
                  r.release_reason,
                  r.release_comment,
                ])
              )
            }}
          >
            <Download className='size-4' />
            {t('mes.export')}
          </Button>
          <Label className='flex items-center gap-2 font-normal'>
            <Switch
              checked={showTerminal}
              onCheckedChange={(v) => {
                setShowTerminal(v)
                setSel([])
              }}
              data-testid='show-terminal'
            />
            {t('mes.holdrel.showTerminal')}
          </Label>
          {canRelease && (
            <Button
              disabled={sel.length === 0}
              onClick={() => setReleasing(sel)}
              data-testid='open-batch-release'
            >
              <Unlock className='size-4' />
              {t('mes.holdrel.release')} ({sel.length})
            </Button>
          )}
        </>
      }
    >
      <DataTable
        rows={rows}
        total={total}
        params={lp}
        filters={filters}
        loading={q.isLoading}
        rowKey={(r) => r.id}
        columns={[
          ...(canRelease
            ? [
                {
                  header: '',
                  headerNode: (
                    <Checkbox
                      checked={allOn}
                      disabled={!activeView.length}
                      onCheckedChange={toggleAll}
                      aria-label={t('mes.holdrel.selectAll')}
                    />
                  ),
                  className: 'w-8',
                  cell: (r: HoldRow) =>
                    r.is_active ? (
                      <Checkbox
                        checked={sel.includes(r.id)}
                        aria-label={r.lot}
                        onCheckedChange={(v) => {
                          setSelLots((m) => ({ ...m, [r.id]: r.lot }))
                          setSel((s) =>
                            v ? [...s, r.id] : s.filter((x) => x !== r.id)
                          )
                        }}
                      />
                    ) : null,
                },
              ]
            : []),
          {
            header: t('mes.holdrel.lot'),
            sortKey: 'lot',
            cell: (r) => (
              <RefLink target='lot' id={r.lot_id} label={r.lot} mono />
            ),
          },
          ...(rows.some((r) => r.lot_status != null)
            ? [
                {
                  header: t('mes.holdrel.lotStatus'),
                  cell: (r: HoldRow) =>
                    r.lot_status ? (
                      <span data-testid='hold-lot-status'>
                        {enumLabel('lot_status', r.lot_status)}
                      </span>
                    ) : (
                      '—'
                    ),
                },
              ]
            : []),
          {
            header: t('mes.holdrel.product'),
            sortKey: 'product',
            cell: (r) => r.product ?? '—',
          },
          {
            header: t('mes.holdrel.step'),
            sortKey: 'step_seq',
            cell: (r) => r.step_seq ?? '—',
          },
          {
            header: t('mes.holdrel.reason'),
            sortKey: 'reason',
            cell: (r) =>
              r.reason ? `${r.reason} · ${r.reason_name ?? ''}` : '—',
          },
          {
            header: t('mes.holdrel.source'),
            cell: (r) => srcLabel(r.source),
          },
          {
            header: t('mes.holdrel.heldAt'),
            sortKey: 'held_at',
            cell: (r) => (r.held_at ? fmtDateTime(r.held_at) : '—'),
          },
          {
            header: t('mes.holdrel.heldBy'),
            cell: (r) => r.held_by ?? '—',
          },
          {
            header: t('mes.holdrel.hours'),
            sortKey: 'hours',
            className: 'text-right tabular-nums',
            cell: (r) => r.hours ?? '—',
          },
          {
            header: t('mes.holdrel.comment'),
            className: 'max-w-48 truncate',
            cell: (r) => r.comment ?? '',
          },
          ...(showRelease
            ? [
                {
                  header: t('mes.holdrel.state'),
                  cell: (r: HoldRow) =>
                    r.is_active ? (
                      <Badge variant='destructive'>
                        {t('mes.holdrel.status.active')}
                      </Badge>
                    ) : (
                      <Badge variant='secondary'>
                        {t('mes.holdrel.status.released')}
                      </Badge>
                    ),
                },
                {
                  header: t('mes.holdrel.releasedAt'),
                  sortKey: 'released_at',
                  cell: (r: HoldRow) =>
                    r.released_at ? fmtDateTime(r.released_at) : '—',
                },
                {
                  header: t('mes.holdrel.releasedBy'),
                  cell: (r: HoldRow) => r.released_by ?? '—',
                },
                {
                  header: t('mes.holdrel.releaseReason'),
                  cell: (r: HoldRow) => r.release_reason ?? '—',
                },
              ]
            : []),
          {
            header: '',
            cell: (r) =>
              canRelease && r.is_active ? (
                <Button
                  size='icon'
                  variant='ghost'
                  title={t('mes.exec.release')}
                  aria-label={t('mes.exec.release')}
                  onClick={() => setReleasing([r.id])}
                >
                  <PlayCircle className='size-4' />
                </Button>
              ) : null,
          },
        ]}
      />
      {releasing && (
        <ReleaseDialog
          ids={releasing}
          lots={releasing.map(
            (id) => selLots[id] ?? rows.find((r) => r.id === id)?.lot ?? id
          )}
          onClose={(done) => {
            setReleasing(null)
            if (done) setSel([])
          }}
        />
      )}
    </Page>
  )
}

/** 释放对话框（单条 / 批量共用）：释放原因代码 + 备注。 */
function ReleaseDialog({
  ids,
  lots,
  onClose,
}: {
  ids: string[]
  lots: string[]
  onClose: (done: boolean) => void
}) {
  const qc = useQueryClient()
  const [reason, setReason] = useState('')
  const [comment, setComment] = useState('')
  const reasons = useQuery({
    queryKey: ['mes', 'reason_code', 'release-options'],
    queryFn: () =>
      mesApi.list('reason_code', { reason_type: 'release', page_size: 100 }),
  })
  const m = useMutation({
    mutationFn: () =>
      execApi.releaseBatch({
        hold_ids: ids,
        reason_id: reason,
        comment: comment || undefined,
      }),
    onSuccess: (r) => {
      const msg = t('mes.holdrel.released', {
        ok: r.released.length,
        bad: r.failed.length,
      })
      if (r.failed.length) toast.warning(msg)
      else toast.success(msg)
      qc.invalidateQueries({ queryKey: ['mes'] })
      onClose(true)
    },
    onError: (e) => toast.error(mesErrorMessage(e, undefined)),
  })
  const title =
    ids.length > 1 ? t('mes.holdrel.release') : t('mes.exec.release')
  return (
    <Dialog open onOpenChange={(o) => !o && onClose(false)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {ids.length > 1
              ? t('mes.holdrel.selected', { n: ids.length })
              : lots.join(', ')}
          </DialogDescription>
        </DialogHeader>
        <Pick
          id='batch-reason'
          label={t('mes.exec.reason')}
          required
          none={false}
          value={reason}
          onChange={setReason}
          options={(reasons.data?.data ?? []).map((r) => ({
            id: String(r.id),
            label: optLabel(r as { code: string; name?: string }),
          }))}
        />
        <div className='grid gap-1'>
          <Label htmlFor='batch-comment'>{t('mes.exec.comment')}</Label>
          <Textarea
            id='batch-comment'
            rows={2}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button
            disabled={!reason || m.isPending}
            onClick={() => m.mutate()}
            data-testid='confirm-release'
          >
            {title}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
