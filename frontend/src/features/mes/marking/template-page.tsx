/** 打标模板页面（P3-F4）：列表（每模板一行）、编辑草稿、审批、新版本、版本列表（D90-3）。 */
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { toast } from 'sonner'
import { useMe } from '@/lib/api/hooks'
import {
  DATE_CODE_BASES,
  isEditable,
  isSelfApproval,
  MARKING_MOCK,
  markingApi,
  markingSignature,
  setMarkingMockUser,
  unknownPlaceholders,
  TEMPLATE_STATUSES,
  type MarkingTemplate,
  type TemplateInput,
} from '@/lib/api/mes/marking'
import { cn } from '@/lib/utils'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { Page } from '@/components/crud'
import { useOperationKey } from '@/features/mes/common/idem-key'
import { useMesCan } from '@/features/mes/common/mes-perm'
import { MARKING_PERM, markingErrorMessage } from './marking-rules'

const KEY = ['mes', 'marking', 'templates']
const dash = (v: unknown) => (v == null || v === '' ? '—' : String(v))

/** 模板状态徽标。 */
function StatusBadge({ status }: { status: string }) {
  const tone =
    status === 'approved'
      ? 'default'
      : status === 'draft'
        ? 'secondary'
        : 'outline'
  return (
    <Badge variant={tone} data-testid={`tpl-status-${status}`}>
      {t(`mes.marking.status.${status}`)}
    </Badge>
  )
}

/** mock 模式下把当前登录用户同步给 mock（自批判断）。 */
function useMeName() {
  const { data: me } = useMe()
  const name = me?.username ?? null
  useEffect(() => {
    if (MARKING_MOCK && name) setMarkingMockUser(name)
  }, [name])
  return name
}

/** 模板列表页（菜单组件 key `mes-page:marking-template`）。 */
export default function MarkingTemplatePage() {
  const can = useMesCan()
  const me = useMeName()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [sel, setSel] = useState<string | null>(null)
  const [edit, setEdit] = useState<MarkingTemplate | 'new' | null>(null)
  const list = useQuery({
    queryKey: KEY,
    queryFn: () => markingApi.templates(),
  })
  const rows = (list.data ?? []).filter(
    (r) =>
      (!status || r.status === status) &&
      (!q ||
        `${r.code} ${r.product_name ?? ''} ${r.customer_name ?? ''}`
          .toLowerCase()
          .includes(q.toLowerCase()))
  )
  const cur = list.data?.find((r) => r.id === sel)
  return (
    <Page
      title={t('mes.marking.tplTitle')}
      description={
        MARKING_MOCK ? t('mes.marking.mockHint') : t('mes.marking.tplDesc')
      }
    >
      <div className='flex flex-wrap gap-2'>
        <Input
          className='w-56'
          placeholder={t('mes.marking.search')}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          data-testid='tpl-search'
        />
        <select
          className='rounded-md border border-input bg-transparent px-2 text-sm'
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          aria-label={t('mes.marking.col.status')}
          data-testid='tpl-status-filter'
        >
          <option value=''>{t('mes.marking.allStatus')}</option>
          {TEMPLATE_STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(`mes.marking.status.${s}`)}
            </option>
          ))}
        </select>
        {can(MARKING_PERM.templateWrite) && (
          <Button onClick={() => setEdit('new')} data-testid='tpl-new'>
            {t('mes.marking.newTpl')}
          </Button>
        )}
      </div>
      <Table data-testid='tpl-list'>
        <TableHeader>
          <TableRow>
            {['code', 'product', 'customer', 'version', 'status'].map((c) => (
              <TableHead key={c}>{t(`mes.marking.col.${c}`)}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow
              key={r.id}
              onClick={() => setSel(r.id)}
              className={cn('cursor-pointer', r.id === sel && 'bg-muted')}
              data-testid={`tpl-row-${r.code}-v${r.version}`}
            >
              <TableCell>{r.code}</TableCell>
              <TableCell>{dash(r.product_name ?? r.product_id)}</TableCell>
              <TableCell>{dash(r.customer_name ?? r.customer_id)}</TableCell>
              <TableCell>v{r.version}</TableCell>
              <TableCell>
                <StatusBadge status={r.status} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {cur && (
        <TemplateDetail
          tpl={cur}
          all={list.data ?? []}
          me={me}
          onEdit={() => setEdit(cur)}
          onNewVersion={(id) => setSel(id)}
        />
      )}
      {edit && (
        <TemplateDialog
          tpl={edit === 'new' ? null : edit}
          onClose={(id) => {
            setEdit(null)
            if (id) setSel(id)
          }}
        />
      )}
    </Page>
  )
}

/** 模板详情：字段、打标行、审批信息、动作、版本对比。 */
function TemplateDetail({
  tpl,
  all,
  me,
  onEdit,
  onNewVersion,
}: {
  tpl: MarkingTemplate
  all: MarkingTemplate[]
  me: string | null
  onEdit: () => void
  onNewVersion: (id: string) => void
}) {
  const can = useMesCan()
  const qc = useQueryClient()
  const self = isSelfApproval(tpl, me)
  // D81/D82：审批、新版本每次操作一个 Idempotency-Key，重试沿用，成功后换新
  const approveKey = useOperationKey()
  const nvKey = useOperationKey()
  const act = useMutation({
    // retired 只在新版本批准后自动产生，没有手动停用（D89 补充一）
    mutationFn: () =>
      markingApi.approve(tpl.id, approveKey.key(`approve:${tpl.id}`)),
    onSuccess: () => {
      approveKey.done()
      toast.success(t('mes.marking.done.approve'))
      void qc.invalidateQueries({ queryKey: KEY })
    },
    onError: (e) => toast.error(markingErrorMessage(e)),
  })
  // D79-1：POST .../{id}/versions 复制最新版本为草稿，版本号后端递增
  const nv = useMutation({
    mutationFn: () =>
      markingApi.newVersion(tpl.id, nvKey.key(`version:${tpl.id}`)),
    onSuccess: (r) => {
      nvKey.done()
      toast.success(t('mes.marking.done.newVersion', { v: r.version }))
      void qc.invalidateQueries({ queryKey: KEY })
      onNewVersion(r.id)
    },
    onError: (e) => toast.error(markingErrorMessage(e)),
  })
  const draft = all.some(
    (x) =>
      x.product_id === tpl.product_id &&
      x.customer_id === tpl.customer_id &&
      x.status === 'draft'
  )
  return (
    <div
      className='mt-4 grid gap-4 rounded-md border p-4'
      data-testid='tpl-detail'
    >
      <div className='flex flex-wrap items-center gap-2'>
        <h3 className='font-semibold'>
          {tpl.code} v{tpl.version}
        </h3>
        <StatusBadge status={tpl.status} />
        <div className='ms-auto flex flex-wrap gap-2'>
          {can(MARKING_PERM.templateWrite) && isEditable(tpl) && (
            <Button variant='outline' onClick={onEdit} data-testid='tpl-edit'>
              {t('mes.marking.edit')}
            </Button>
          )}
          {can(MARKING_PERM.templateWrite) &&
            tpl.status !== 'draft' &&
            !draft && (
              <Button
                variant='outline'
                onClick={() => nv.mutate()}
                disabled={nv.isPending}
                data-testid='tpl-new-version'
              >
                {t('mes.marking.newVersion')}
              </Button>
            )}
          {can(MARKING_PERM.templateApprove) && tpl.status === 'draft' && (
            <Button
              onClick={() => act.mutate()}
              disabled={self || act.isPending}
              title={self ? t('mes.marking.selfApprovalHint') : undefined}
              data-testid='tpl-approve'
            >
              {t('mes.marking.approve')}
            </Button>
          )}
        </div>
      </div>
      {self && tpl.status === 'draft' && can(MARKING_PERM.templateApprove) && (
        <p
          className='text-sm text-muted-foreground'
          data-testid='tpl-self-hint'
        >
          {t('mes.marking.selfApprovalHint')}
        </p>
      )}
      <dl className='grid grid-cols-2 gap-2 text-sm md:grid-cols-4'>
        <Info k='product' v={tpl.product_name ?? tpl.product_id} />
        <Info k='customer' v={tpl.customer_name ?? tpl.customer_id} />
        <Info
          k='dateCodeBasis'
          v={t(`mes.marking.basis.${tpl.date_code_basis}`)}
        />
        <Info k='usesBin' v={t(tpl.uses_bin ? 'common.yes' : 'common.no')} />
        <Info k='createdBy' v={tpl.created_by} />
        <Info k='createdAt' v={tpl.created_at && fmtDateTime(tpl.created_at)} />
        <Info k='approvedBy' v={tpl.approved_by} />
        <Info
          k='approvedAt'
          v={tpl.approved_at && fmtDateTime(tpl.approved_at)}
        />
      </dl>
      <div>
        <p className='mb-1 text-sm font-medium'>{t('mes.marking.col.lines')}</p>
        <pre
          className='rounded bg-muted p-2 font-mono text-sm'
          data-testid='tpl-lines'
        >
          {tpl.lines.join('\n')}
        </pre>
      </div>
      <VersionList id={tpl.id} />
    </div>
  )
}

function Info({ k, v }: { k: string; v: unknown }) {
  return (
    <div>
      <dt className='text-muted-foreground'>{t(`mes.marking.col.${k}`)}</dt>
      <dd>{dash(v)}</dd>
    </div>
  )
}

/** D90-3：详情 versions[]（version 倒序；未批准的 approved_by/approved_at 为 null）。 */
export function VersionList({ id }: { id: string }) {
  const q = useQuery({
    queryKey: [...KEY, 'detail', id],
    queryFn: () => markingApi.template(id),
  })
  const vs = q.data?.versions ?? []
  return (
    <Table data-testid='tpl-versions'>
      <TableHeader>
        <TableRow>
          {(
            [
              'version',
              'status',
              'createdBy',
              'createdAt',
              'approvedBy',
              'approvedAt',
            ] as const
          ).map((c) => (
            <TableHead key={c}>{t(`mes.marking.col.${c}`)}</TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {vs.map((v) => (
          <TableRow key={v.version} data-testid={`tpl-version-v${v.version}`}>
            <TableCell>v{v.version}</TableCell>
            <TableCell>
              <StatusBadge status={v.status} />
            </TableCell>
            <TableCell>{dash(v.created_by)}</TableCell>
            <TableCell>
              {dash(v.created_at && fmtDateTime(v.created_at))}
            </TableCell>
            <TableCell>{dash(v.approved_by)}</TableCell>
            <TableCell>
              {dash(v.approved_at && fmtDateTime(v.approved_at))}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

/** 新建 / 编辑草稿 / 基于已有版本新建版本（tpl.id 为空）。 */
function TemplateDialog({
  tpl,
  onClose,
}: {
  tpl: MarkingTemplate | null
  onClose: (id?: string) => void
}) {
  const qc = useQueryClient()
  const editing = !!tpl?.id
  const [f, setF] = useState<TemplateInput>({
    code: tpl?.code ?? '',
    product_id: tpl?.product_id ?? '',
    customer_id: tpl?.customer_id ?? '',
    lines: tpl?.lines ?? ['{product_code}', '{date_code}{trace_code}'],
    date_code_basis: tpl?.date_code_basis ?? 'marking',
    uses_bin: tpl?.uses_bin ?? false,
  })
  const [err, setErr] = useState('')
  // D81/D82：保存每次操作一个 Idempotency-Key；内容不变的重试沿用，内容变了换新
  const saveKey = useOperationKey()
  const save = useMutation({
    mutationFn: () => {
      if (editing) {
        const body = {
          lines: f.lines,
          date_code_basis: f.date_code_basis,
          uses_bin: f.uses_bin,
        }
        return markingApi.updateTemplate(
          tpl.id,
          body,
          saveKey.key(markingSignature(`tpl-update:${tpl.id}`, body))
        )
      }
      return markingApi.createTemplate(
        f,
        saveKey.key(markingSignature('tpl-create', f))
      )
    },
    onSuccess: (r) => {
      saveKey.done()
      toast.success(t('mes.marking.done.save'))
      void qc.invalidateQueries({ queryKey: KEY })
      onClose(r.id)
    },
    onError: (e) => setErr(markingErrorMessage(e)),
  })
  const unknown = unknownPlaceholders(f.lines)
  const text = (k: 'code' | 'product_id' | 'customer_id', label: string) => (
    <div className='grid gap-1'>
      <Label htmlFor={`tpl-${k}`}>{label}</Label>
      <Input
        id={`tpl-${k}`}
        value={f[k]}
        disabled={editing}
        onChange={(e) => setF({ ...f, [k]: e.target.value })}
        data-testid={`tpl-f-${k}`}
      />
    </div>
  )
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {editing ? t('mes.marking.edit') : t('mes.marking.newTpl')}
          </DialogTitle>
          <DialogDescription>{t('mes.marking.formHint')}</DialogDescription>
        </DialogHeader>
        <div className='grid gap-3'>
          {text('code', t('mes.marking.col.code'))}
          {text('product_id', t('mes.marking.col.product'))}
          {text('customer_id', t('mes.marking.col.customer'))}
          <div className='grid gap-1'>
            <Label htmlFor='tpl-basis'>
              {t('mes.marking.col.dateCodeBasis')}
            </Label>
            <select
              id='tpl-basis'
              className='rounded-md border border-input bg-transparent px-2 py-1 text-sm'
              value={f.date_code_basis}
              onChange={(e) =>
                setF({
                  ...f,
                  date_code_basis: e.target
                    .value as TemplateInput['date_code_basis'],
                })
              }
            >
              {DATE_CODE_BASES.map((b) => (
                <option key={b} value={b}>
                  {t(`mes.marking.basis.${b}`)}
                </option>
              ))}
            </select>
          </div>
          <label className='flex items-center gap-2 text-sm'>
            <input
              type='checkbox'
              checked={f.uses_bin}
              onChange={(e) => setF({ ...f, uses_bin: e.target.checked })}
              data-testid='tpl-f-uses-bin'
            />
            {t('mes.marking.col.usesBin')}
          </label>
          <div className='grid gap-1'>
            <Label htmlFor='tpl-lines'>{t('mes.marking.col.lines')}</Label>
            <Textarea
              id='tpl-lines'
              className='font-mono'
              value={f.lines.join('\n')}
              onChange={(e) =>
                setF({ ...f, lines: e.target.value.split('\n') })
              }
              data-testid='tpl-f-lines'
            />
            <p className='text-xs text-muted-foreground'>
              {t('mes.marking.linesHint')}
            </p>
            {unknown.map((n) => (
              <p
                key={n}
                className='text-sm text-destructive'
                data-testid='tpl-err-placeholder'
              >
                {t('mes.marking.err.unknownPlaceholder', { name: `{${n}}` })}
              </p>
            ))}
          </div>
          {err && (
            <p className='text-sm text-destructive' data-testid='tpl-err'>
              {err}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => onClose()}>
            {t('common.cancel')}
          </Button>
          <Button
            onClick={() => {
              setErr('')
              save.mutate()
            }}
            disabled={save.isPending || unknown.length > 0}
            data-testid='tpl-save'
          >
            {t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
