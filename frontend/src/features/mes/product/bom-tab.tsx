/**
 * 产品详情的 BOM 页签（F3，bom.md v1.1，验收见 f3-acceptance.md）。
 *
 * 版本列表（草稿 / 生效 / 已取代 / 作废）+ 选中版本的明细；新建草稿、编辑草稿、
 * 生效、作废、复制。只有草稿可编辑，其他状态只读，按钮置灰并在悬停 / 聚焦时说明原因（FE-02）。
 * 没有权限时按钮全部置灰；后端 403 只提示无权限（D34）。生效 / 作废 / 复制请求体为空（D32）。
 * 明细按两级树展示：半成品行（component_type=product）可展开，只读显示该半成品当前生效的版本，
 * 维护要到该产品自己的 BOM 页签（§7.1）。草稿里可编辑替代料（§7.2），保存见 `bom-save.ts`。
 * 用量比对（F4）和单位换算维护（F8）不在本页签。
 */
import { type ReactNode, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import {
  bomApi,
  type Bom,
  type BomLine,
  type BomNode,
  type BomStatus,
} from '@/lib/api/mes/bom'
import type { MesRow } from '@/lib/api/mes/common'
import { Badge } from '@/components/ui/badge'
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
import { ConfirmDialog } from '@/components/confirm-dialog'
import { IconTooltip } from '@/components/icon-button'
import { MES_PERM, useMesCan } from '@/features/mes/common/mes-perm'
import { RefLink } from '@/features/mes/common/ref-link'
import { RefSelect } from '@/features/mes/common/ref-select'
import { useMesEntity } from '@/features/mes/common/use-mes-meta'
import { bomError, type BomFieldError } from './bom-errors'
import {
  BomSaveError,
  type LineDraft,
  saveDraft,
  type SubDraft,
  toLineDraft,
} from './bom-save'

const PER_BASIS = ['wafer', 'strip', 'die', 'package', 'unit', 'lot'] as const
const CONSUME = ['issue', 'mounted'] as const
const COMPONENT_TYPES = ['material', 'product'] as const

const STATUS_VARIANT: Record<
  BomStatus,
  'default' | 'secondary' | 'outline' | 'destructive'
> = {
  draft: 'outline',
  active: 'default',
  superseded: 'secondary',
  void: 'destructive',
}

/** 状态的本地化名称。 */
const statusLabel = (s: string) => t(`mes.bomTab.status.${s}`)

/** 数量原样显示（后端 Decimal(18,6)，前端不四舍五入）。 */
const qtyText = (q: number | string | null | undefined) =>
  q == null ? '—' : String(q)

/** BOM 权限：写（新建 / 编辑 / 复制）与生效（生效 / 作废）。 */
function useBomPerms() {
  const can = useMesCan()
  const { entity } = useMesEntity('bom')
  return {
    write: !!entity?.can_write || can(MES_PERM.bomWrite),
    activate: can(MES_PERM.bomActivate),
  }
}

/** 按钮：禁用时外包可聚焦的 span，悬停 / 键盘聚焦显示原因。 */
function ActionButton({
  label,
  reason,
  onClick,
  variant = 'outline',
  pending,
}: {
  label: string
  /** 禁用原因；为空表示可用 */
  reason: string | null
  onClick: () => void
  variant?: 'outline' | 'default' | 'destructive'
  pending?: boolean
}) {
  if (!reason)
    return (
      <Button size='sm' variant={variant} onClick={onClick} disabled={pending}>
        {label}
      </Button>
    )
  return (
    <IconTooltip label={reason}>
      <span
        tabIndex={0}
        className='inline-flex'
        aria-label={`${label}: ${reason}`}
        data-testid='bom-disabled-reason'
      >
        <Button size='sm' variant={variant} disabled tabIndex={-1}>
          {label}
        </Button>
      </span>
    </IconTooltip>
  )
}

/** 产品详情的 BOM 页签。 */
export function BomTab({ row }: { row: MesRow }) {
  const tk = useTenantKey()
  const qc = useQueryClient()
  const perms = useBomPerms()
  const [selected, setSelected] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState(false)
  const [confirm, setConfirm] = useState<'activate' | 'void' | null>(null)
  const listKey = ['mes', 'bom', 'versions', tk, row.id]
  const versions = useQuery({
    queryKey: listKey,
    queryFn: () => bomApi.list(row.id),
    retry: false,
  })
  const list = versions.data ?? []
  const current =
    list.find((b) => b.id === selected) ??
    list.find((b) => b.status === 'draft') ??
    list.find((b) => b.status === 'active') ??
    list[list.length - 1]
  const tree = useQuery({
    queryKey: ['mes', 'bom', 'tree', tk, current?.id],
    queryFn: () => bomApi.tree(current!.id),
    enabled: !!current,
    retry: false,
  })
  const refresh = () => qc.invalidateQueries({ queryKey: ['mes', 'bom'] })
  const action = useMutation({
    mutationFn: ({
      kind,
      id,
    }: {
      kind: 'activate' | 'void' | 'copy'
      id: string
    }) => bomApi[kind](id),
    onSuccess: (b, v) => {
      toast.success(t(`mes.bomTab.done.${v.kind}`, { version: b.version }))
      setSelected(b.id)
      setConfirm(null)
    },
    onError: (e) => {
      toast.error(bomError(e).message)
      setConfirm(null)
    },
    onSettled: refresh,
  })

  const noWrite = perms.write ? null : t('mes.bomTab.reason.noPermission')
  const noActivate = perms.activate ? null : t('mes.bomTab.reason.noPermission')
  const status = current?.status
  const notDraft =
    status && status !== 'draft'
      ? t('mes.bomTab.reason.notDraft', { status: statusLabel(status) })
      : null
  const voidReason =
    status === 'superseded' || status === 'void'
      ? t('mes.bomTab.reason.cannotVoid', { status: statusLabel(status) })
      : null

  if (versions.error)
    return (
      <p className='pt-2 text-destructive' role='alert'>
        {bomError(versions.error).message}
      </p>
    )

  return (
    <div className='space-y-4 pt-2' data-testid='bom-tab'>
      <div className='flex items-center justify-between gap-2'>
        <h3 className='font-semibold'>{t('mes.bomTab.versions')}</h3>
        <ActionButton
          label={t('mes.bomTab.create')}
          reason={noWrite}
          variant='default'
          onClick={() => setCreating(true)}
        />
      </div>
      {versions.isLoading ? null : list.length === 0 ? (
        <p className='text-sm text-muted-foreground'>{t('mes.bomTab.empty')}</p>
      ) : (
        <table className='w-full text-sm' aria-label={t('mes.bomTab.versions')}>
          <thead className='text-left text-muted-foreground'>
            <tr>
              <th className='py-1'>{t('mes.bomTab.col.version')}</th>
              <th>{t('mes.bomTab.col.status')}</th>
              <th>{t('mes.bomTab.col.description')}</th>
              <th>{t('mes.bomTab.col.effectiveAt')}</th>
              <th>{t('mes.bomTab.col.copiedFrom')}</th>
              <th>{t('mes.bomTab.col.createdAt')}</th>
            </tr>
          </thead>
          <tbody>
            {list.map((b) => (
              <tr
                key={b.id}
                data-testid={`bom-version-${b.version}`}
                aria-selected={b.id === current?.id}
                className={b.id === current?.id ? 'bg-muted' : undefined}
              >
                <td className='py-1'>
                  <Button
                    size='sm'
                    variant='link'
                    className='h-auto p-0'
                    onClick={() => setSelected(b.id)}
                  >
                    v{b.version}
                  </Button>
                </td>
                <td>
                  <Badge variant={STATUS_VARIANT[b.status]}>
                    {statusLabel(b.status)}
                  </Badge>
                </td>
                <td>{b.description ?? '—'}</td>
                <td>{fmtDateTime(b.effective_at) || '—'}</td>
                <td>{b.copied_from_label ?? '—'}</td>
                <td>{fmtDateTime(b.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {current && (
        <section className='space-y-2' aria-label={t('mes.bomTab.lines')}>
          <div className='flex flex-wrap items-center gap-2'>
            <h3 className='mr-auto font-semibold'>
              {t('mes.bomTab.linesOf', { version: current.version })}
            </h3>
            <ActionButton
              label={t('mes.bomTab.edit')}
              reason={noWrite ?? notDraft}
              onClick={() => setEditing(true)}
            />
            <ActionButton
              label={t('mes.bomTab.activate')}
              reason={noActivate ?? notDraft}
              onClick={() => setConfirm('activate')}
            />
            <ActionButton
              label={t('mes.bomTab.void')}
              reason={noActivate ?? voidReason}
              variant='destructive'
              onClick={() => setConfirm('void')}
            />
            <ActionButton
              label={t('mes.bomTab.copy')}
              reason={noWrite}
              pending={action.isPending}
              onClick={() => action.mutate({ kind: 'copy', id: current.id })}
            />
          </div>
          <LinesTable lines={tree.data?.lines ?? []} loading={tree.isLoading} />
        </section>
      )}

      <CreateDialog
        open={creating}
        productId={row.id}
        onClose={() => setCreating(false)}
        onCreated={(b) => {
          setSelected(b.id)
          setCreating(false)
          void refresh()
        }}
      />
      {current && editing && tree.data && (
        <EditDialog
          bom={current}
          lines={tree.data.lines}
          onClose={() => {
            setEditing(false)
            void refresh()
          }}
        />
      )}
      {current && (
        <ConfirmDialog
          open={!!confirm}
          onOpenChange={(o) => !o && setConfirm(null)}
          title={
            confirm
              ? t(`mes.bomTab.confirm.${confirm}Title`, {
                  version: current.version,
                })
              : ''
          }
          desc={confirm ? t(`mes.bomTab.confirm.${confirm}Desc`) : ''}
          confirmText={confirm ? t(`mes.bomTab.${confirm}`) : undefined}
          destructive={confirm === 'void'}
          isLoading={action.isPending}
          handleConfirm={() =>
            confirm && action.mutate({ kind: confirm, id: current.id })
          }
        />
      )}
    </div>
  )
}

const COLS = 7

function LinesTable({
  lines,
  loading,
}: {
  lines: BomLine[]
  loading: boolean
}) {
  const [open, setOpen] = useState<Set<string>>(new Set())
  if (loading) return null
  if (!lines.length)
    return (
      <p className='text-sm text-muted-foreground'>{t('mes.bomTab.noLines')}</p>
    )
  const toggle = (id: string) =>
    setOpen((o) => {
      const n = new Set(o)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  return (
    <table className='w-full text-sm' data-testid='bom-lines'>
      <LinesHead />
      <tbody>
        {lines.map((l) => (
          <LineRows
            key={l.id}
            line={l}
            expanded={open.has(l.id)}
            onToggle={() => toggle(l.id)}
          />
        ))}
      </tbody>
    </table>
  )
}

function LinesHead() {
  return (
    <thead className='text-left text-muted-foreground'>
      <tr>
        <th className='py-1'>{t('mes.bomTab.col.lineNo')}</th>
        <th>{t('mes.bomTab.col.component')}</th>
        <th>{t('mes.bomTab.col.qty')}</th>
        <th>{t('mes.bomTab.col.uom')}</th>
        <th>{t('mes.bomTab.col.perBasis')}</th>
        <th>{t('mes.bomTab.col.scrapRate')}</th>
        <th>{t('mes.bomTab.col.consumeMode')}</th>
      </tr>
    </thead>
  )
}

/** 一行明细；半成品行可展开（只读）其当前生效版本。 */
function LineRows({
  line: l,
  expanded,
  onToggle,
}: {
  line: BomLine
  /** undefined 表示不可展开（第二级） */
  expanded?: boolean
  onToggle?: () => void
}) {
  const product = l.component_type === 'product'
  const name = l.component_product_label ?? l.component_product_id ?? '—'
  const subs = l.substitutes ?? []
  return (
    <>
      <tr data-testid={`bom-line-${l.line_no}`}>
        <td className='py-1 align-top'>{l.line_no}</td>
        <td className='align-top'>
          {product ? (
            <span className='inline-flex items-center gap-1'>
              {onToggle && (
                <Button
                  size='sm'
                  variant='ghost'
                  className='h-6 px-1'
                  aria-expanded={expanded}
                  aria-label={t(
                    expanded ? 'mes.bomTab.collapse' : 'mes.bomTab.expand',
                    { name }
                  )}
                  onClick={onToggle}
                >
                  {expanded ? '▾' : '▸'}
                </Button>
              )}
              <Badge variant='secondary'>
                {t('mes.bomTab.componentType.product')}
              </Badge>
              {l.component_product_id ? (
                <RefLink
                  target='product'
                  id={l.component_product_id}
                  label={name}
                />
              ) : (
                name
              )}
            </span>
          ) : (
            (l.material_label ?? '—')
          )}
          {subs.length > 0 && (
            <div
              className='text-xs text-muted-foreground'
              data-testid='bom-line-subs'
            >
              {t('mes.bomTab.subOf', {
                list: subs
                  .map(
                    (x) => `${x.priority}. ${x.material_label ?? x.material_id}`
                  )
                  .join('，'),
              })}
            </div>
          )}
        </td>
        <td className='align-top' data-testid='bom-line-qty'>
          {qtyText(l.qty)}
        </td>
        <td className='align-top'>{l.uom_label ?? '—'}</td>
        <td className='align-top'>{t(`mes.bomTab.perBasis.${l.per_basis}`)}</td>
        <td className='align-top'>{qtyText(l.scrap_rate)}</td>
        <td className='align-top'>
          {t(`mes.bomTab.consume.${l.consume_mode}`)}
        </td>
      </tr>
      {product && expanded && (
        <tr data-testid={`bom-child-${l.line_no}`}>
          <td />
          <td colSpan={COLS - 1} className='pb-2'>
            <ChildNode
              node={l.child ?? null}
              productId={l.component_product_id}
              name={name}
            />
          </td>
        </tr>
      )}
    </>
  )
}

/** 第二级：半成品当前生效版本，只读；维护请到该产品。 */
function ChildNode({
  node,
  productId,
  name,
}: {
  node: BomNode | null
  productId: string | null
  name: string
}) {
  return (
    <div className='rounded border-l-2 pl-3' data-testid='bom-child'>
      <div className='flex items-center gap-2 py-1 text-xs text-muted-foreground'>
        <span>
          {node?.bom
            ? t('mes.bomTab.childActive', { version: node.bom.version })
            : t('mes.bomTab.childNone')}
        </span>
        {productId && (
          <RefLink
            target='product'
            id={productId}
            label={`${t('mes.bomTab.maintain')}（${name}）`}
          />
        )}
      </div>
      {node?.bom && node.lines.length > 0 && (
        <table className='w-full text-sm'>
          <LinesHead />
          <tbody>
            {node.lines.map((c) => (
              <LineRows key={c.id} line={c} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function CreateDialog({
  open,
  productId,
  onClose,
  onCreated,
}: {
  open: boolean
  productId: string
  onClose: () => void
  onCreated: (b: Bom) => void
}) {
  const [desc, setDesc] = useState('')
  const m = useMutation({
    mutationFn: () => bomApi.create(productId, desc.trim()),
    onSuccess: (b) => {
      toast.success(t('mes.bomTab.done.create', { version: b.version }))
      setDesc('')
      onCreated(b)
    },
    onError: (e) => toast.error(bomError(e).message),
  })
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('mes.bomTab.createTitle')}</DialogTitle>
          <DialogDescription>{t('mes.bomTab.createDesc')}</DialogDescription>
        </DialogHeader>
        <div className='grid gap-1.5'>
          <Label htmlFor='bom-new-desc'>
            {t('mes.bomTab.col.description')}
          </Label>
          <Input
            id='bom-new-desc'
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button onClick={() => m.mutate()} disabled={m.isPending}>
            {t('mes.bomTab.create')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** 单位下拉选项：来自单位换算两端的单位（另加当前已选单位）。 */
function useUomOptions(extra: { id: string; label: string | null }[]) {
  const tk = useTenantKey()
  const { data } = useQuery({
    queryKey: ['mes', 'bom', 'uom-conversions', tk],
    queryFn: bomApi.conversions,
    staleTime: 60_000,
  })
  return useMemo(() => {
    const m = new Map<string, string>()
    for (const c of data ?? []) {
      m.set(c.from_uom_id, c.from_uom_label ?? c.from_uom_id)
      m.set(c.to_uom_id, c.to_uom_label ?? c.to_uom_id)
    }
    for (const x of extra)
      if (x.id && !m.has(x.id)) m.set(x.id, x.label ?? x.id)
    return [...m.entries()]
      .map(([id, label]) => ({ id, label }))
      .sort((a, b) => a.label.localeCompare(b.label))
  }, [data, extra])
}

function EditDialog({
  bom,
  lines,
  onClose,
}: {
  bom: Bom
  lines: BomLine[]
  onClose: () => void
}) {
  const [desc, setDesc] = useState(bom.description ?? '')
  const [rows, setRows] = useState<LineDraft[]>(() => lines.map(toLineDraft))
  const [errs, setErrs] = useState<BomFieldError[]>([])
  const [banner, setBanner] = useState<string | null>(null)
  const extra = useMemo(
    () => lines.map((l) => ({ id: l.uom_id, label: l.uom_label })),
    [lines]
  )
  const uoms = useUomOptions(extra)
  const set = (i: number, patch: Partial<LineDraft>) =>
    setRows((r) => r.map((x, j) => (j === i ? { ...x, ...patch } : x)))
  const setSub = (i: number, j: number, patch: Partial<SubDraft>) =>
    setRows((r) =>
      r.map((x, k) =>
        k === i
          ? {
              ...x,
              subs: x.subs.map((y, m) => (m === j ? { ...y, ...patch } : y)),
            }
          : x
      )
    )
  const errOf = (line: number | null, field: string) =>
    errs.find((e) => e.line === line && e.field === field)?.message

  const save = useMutation({
    mutationFn: () => {
      setErrs([])
      setBanner(null)
      return saveDraft({ bom, desc, rows })
    },
    onSuccess: () => {
      toast.success(t('mes.bomTab.done.save', { version: bom.version }))
      onClose()
    },
    onError: (x: unknown) => {
      // 整单在一个事务里，失败什么都没改：弹窗不关、输入保留，改完直接重试
      const se = x instanceof BomSaveError ? x : new BomSaveError(x)
      const be = bomError(se.error)
      // loc ["body","lines",k,...] 的 k 是请求下标（D38，从 0 开始），换回编辑框下标
      setErrs(
        be.fields.map((f) =>
          f.line == null ? f : { ...f, line: se.lineMap?.[f.line] ?? f.line }
        )
      )
      setBanner(be.message)
    },
  })

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-5xl'>
        <DialogHeader>
          <DialogTitle>
            {t('mes.bomTab.editTitle', { version: bom.version })}
          </DialogTitle>
          <DialogDescription>{t('mes.bomTab.editDesc')}</DialogDescription>
        </DialogHeader>
        {banner && (
          <p className='text-sm text-destructive' role='alert'>
            {banner}
          </p>
        )}
        <div className='grid gap-1.5'>
          <Label htmlFor='bom-edit-desc'>
            {t('mes.bomTab.col.description')}
          </Label>
          <Input
            id='bom-edit-desc'
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            aria-invalid={!!errOf(null, 'description')}
          />
          <FieldErr msg={errOf(null, 'description')} />
        </div>
        <div className='max-h-[60vh] space-y-3 overflow-y-auto'>
          {rows.map((r, i) =>
            r.removed ? null : (
              <fieldset
                key={r.key}
                className='grid gap-2 rounded border p-2 sm:grid-cols-4'
                data-testid={`bom-edit-line-${i}`}
              >
                <legend className='px-1 text-xs'>
                  {t('mes.bomTab.lineN', { n: r.line_no || i + 1 })}
                </legend>
                <Field
                  id={`l${i}-no`}
                  label={t('mes.bomTab.col.lineNo')}
                  err={errOf(i, 'line_no')}
                >
                  <Input
                    id={`l${i}-no`}
                    inputMode='numeric'
                    value={r.line_no}
                    onChange={(e) => set(i, { line_no: e.target.value })}
                  />
                </Field>
                <Field
                  id={`l${i}-type`}
                  label={t('mes.bomTab.col.componentType')}
                  err={errOf(i, 'component_type')}
                >
                  <NativeSelect
                    id={`l${i}-type`}
                    value={r.component_type}
                    onChange={(v) =>
                      set(i, {
                        component_type: v as LineDraft['component_type'],
                      })
                    }
                    options={COMPONENT_TYPES.map((x) => ({
                      id: x,
                      label: t(`mes.bomTab.componentType.${x}`),
                    }))}
                  />
                </Field>
                {r.component_type === 'product' ? (
                  <Field
                    id={`l${i}-prod`}
                    label={t('mes.bomTab.componentType.product')}
                    err={
                      errOf(i, 'component_product_id') ??
                      errOf(i, 'component_product')
                    }
                  >
                    <RefSelect
                      id={`l${i}-prod`}
                      target='product'
                      value={r.component_product_id}
                      label={r.component_product_label}
                      onChange={(id, label) =>
                        set(i, {
                          component_product_id: id,
                          component_product_label: label,
                        })
                      }
                    />
                  </Field>
                ) : (
                  <Field
                    id={`l${i}-mat`}
                    label={t('mes.bomTab.componentType.material')}
                    err={errOf(i, 'material_id') ?? errOf(i, 'material')}
                  >
                    <RefSelect
                      id={`l${i}-mat`}
                      target='material'
                      value={r.material_id}
                      label={r.material_label}
                      onChange={(id, label) =>
                        set(i, { material_id: id, material_label: label })
                      }
                    />
                  </Field>
                )}
                <Field
                  id={`l${i}-qty`}
                  label={t('mes.bomTab.col.qty')}
                  err={errOf(i, 'qty')}
                >
                  <Input
                    id={`l${i}-qty`}
                    inputMode='decimal'
                    value={r.qty}
                    onChange={(e) => set(i, { qty: e.target.value })}
                  />
                </Field>
                <Field
                  id={`l${i}-uom`}
                  label={t('mes.bomTab.col.uom')}
                  err={errOf(i, 'uom_id') ?? errOf(i, 'uom')}
                >
                  <NativeSelect
                    id={`l${i}-uom`}
                    value={r.uom_id}
                    onChange={(v) => set(i, { uom_id: v })}
                    options={[
                      { id: '', label: t('mes.bomTab.pickUom') },
                      ...uoms,
                    ]}
                  />
                </Field>
                <Field
                  id={`l${i}-basis`}
                  label={t('mes.bomTab.col.perBasis')}
                  err={errOf(i, 'per_basis')}
                >
                  <NativeSelect
                    id={`l${i}-basis`}
                    value={r.per_basis}
                    onChange={(v) => set(i, { per_basis: v })}
                    options={PER_BASIS.map((x) => ({
                      id: x,
                      label: t(`mes.bomTab.perBasis.${x}`),
                    }))}
                  />
                </Field>
                <Field
                  id={`l${i}-scrap`}
                  label={t('mes.bomTab.col.scrapRate')}
                  err={errOf(i, 'scrap_rate')}
                >
                  <Input
                    id={`l${i}-scrap`}
                    inputMode='decimal'
                    value={r.scrap_rate}
                    onChange={(e) => set(i, { scrap_rate: e.target.value })}
                  />
                </Field>
                <Field
                  id={`l${i}-mode`}
                  label={t('mes.bomTab.col.consumeMode')}
                  err={errOf(i, 'consume_mode')}
                >
                  <NativeSelect
                    id={`l${i}-mode`}
                    value={r.consume_mode}
                    onChange={(v) => set(i, { consume_mode: v })}
                    options={CONSUME.map((x) => ({
                      id: x,
                      label: t(`mes.bomTab.consume.${x}`),
                    }))}
                  />
                </Field>
                <div className='flex items-end'>
                  <Button
                    size='sm'
                    variant='ghost'
                    onClick={() => set(i, { removed: true })}
                  >
                    {t('mes.bomTab.removeLine')}
                  </Button>
                </div>
                {r.component_type === 'material' && (
                  <SubEditor
                    line={i}
                    subs={r.subs}
                    errOf={errOf}
                    onChange={(j, patch) => setSub(i, j, patch)}
                    onAdd={() =>
                      set(i, {
                        subs: [
                          ...r.subs,
                          {
                            key: `new-sub-${i}-${r.subs.length}-${Date.now()}`,
                            material_id: null,
                            material_label: null,
                            priority: String(
                              Math.max(
                                0,
                                ...r.subs.map((x) => Number(x.priority) || 0)
                              ) + 1
                            ),
                          },
                        ],
                      })
                    }
                    onRemove={(j) =>
                      set(i, { subs: r.subs.filter((_, k) => k !== j) })
                    }
                  />
                )}
              </fieldset>
            )
          )}
        </div>
        <DialogFooter className='sm:justify-between'>
          <Button
            variant='outline'
            onClick={() => {
              const max = Math.max(
                0,
                ...rows.map((r) => Number(r.line_no) || 0)
              )
              setRows((x) => [
                ...x,
                {
                  key: `new-${x.length}`,
                  line_no: String(max + 10),
                  component_type: 'material',
                  material_id: null,
                  material_label: null,
                  component_product_id: null,
                  component_product_label: null,
                  qty: '',
                  uom_id: '',
                  per_basis: 'wafer',
                  scrap_rate: '0',
                  consume_mode: 'issue',
                  subs: [],
                },
              ])
            }}
          >
            {t('mes.bomTab.addLine')}
          </Button>
          <div className='flex gap-2'>
            <Button variant='outline' onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button onClick={() => save.mutate()} disabled={save.isPending}>
              {t('common.save')}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Field({
  id,
  label,
  err,
  children,
}: {
  id: string
  label: string
  err?: string
  children: ReactNode
}) {
  return (
    <div className='grid gap-1'>
      <Label htmlFor={id}>{label}</Label>
      {children}
      <FieldErr msg={err} id={`${id}-err`} />
    </div>
  )
}

function FieldErr({ msg, id }: { msg?: string; id?: string }) {
  if (!msg) return null
  return (
    <p
      id={id}
      className='text-xs text-destructive'
      data-testid='bom-field-error'
    >
      {msg}
    </p>
  )
}

function NativeSelect({
  id,
  value,
  onChange,
  options,
}: {
  id: string
  value: string
  onChange: (v: string) => void
  options: { id: string; label: string }[]
}) {
  return (
    <select
      id={id}
      className='h-9 rounded-md border border-input bg-background px-2 text-sm'
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {options.map((o) => (
        <option key={o.id} value={o.id}>
          {o.label}
        </option>
      ))}
    </select>
  )
}

/** 草稿里某一物料行的替代料：增删、设置优先级（随 BOM 版本一起生效，§7.2）。 */
function SubEditor({
  line: i,
  subs,
  errOf,
  onChange,
  onAdd,
  onRemove,
}: {
  line: number
  subs: SubDraft[]
  errOf: (line: number | null, field: string) => string | undefined
  onChange: (j: number, patch: Partial<SubDraft>) => void
  onAdd: () => void
  onRemove: (j: number) => void
}) {
  return (
    <div
      className='space-y-2 sm:col-span-4'
      data-testid={`bom-edit-subs-${i}`}
      role='group'
      aria-label={t('mes.bomTab.col.substitutes')}
    >
      <div className='flex items-center gap-2 text-xs text-muted-foreground'>
        <span className='font-medium text-foreground'>
          {t('mes.bomTab.col.substitutes')}
        </span>
        <span>
          {subs.length ? t('mes.bomTab.subHint') : t('mes.bomTab.subNone')}
        </span>
        <FieldErr
          msg={errOf(i, 'priority') ?? errOf(i, 'bom_line')}
          id={`l${i}-subs-err`}
        />
      </div>
      {subs.map((s, j) => (
        <div
          key={s.key}
          className='grid gap-2 sm:grid-cols-[1fr_8rem_auto]'
          data-testid={`bom-edit-sub-${i}-${j}`}
        >
          <Field
            id={`l${i}-s${j}-mat`}
            label={t('mes.bomTab.subMaterial')}
            err={
              errOf(i, `sub.${j}.material`) ?? errOf(i, `sub.${j}.material_id`)
            }
          >
            <RefSelect
              id={`l${i}-s${j}-mat`}
              target='material'
              value={s.material_id}
              label={s.material_label}
              onChange={(id, label) =>
                onChange(j, { material_id: id, material_label: label })
              }
            />
          </Field>
          <Field
            id={`l${i}-s${j}-pri`}
            label={t('mes.bomTab.subPriority')}
            err={errOf(i, `sub.${j}.priority`)}
          >
            <Input
              id={`l${i}-s${j}-pri`}
              inputMode='numeric'
              value={s.priority}
              onChange={(e) => onChange(j, { priority: e.target.value })}
            />
          </Field>
          <div className='flex items-end'>
            <Button size='sm' variant='ghost' onClick={() => onRemove(j)}>
              {t('mes.bomTab.removeSub')}
            </Button>
          </div>
        </div>
      ))}
      <Button size='sm' variant='outline' onClick={onAdd}>
        {t('mes.bomTab.addSub')}
      </Button>
    </div>
  )
}
