/** MES 实体新增 / 编辑表单。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Loader2 } from 'lucide-react'
import { useTenantKey } from '@/lib/api/hooks'
import {
  mesApi,
  type MesEntity,
  type MesField,
  type MesRow,
} from '@/lib/api/mes/common'
import { decimalText } from '@/lib/decimal'
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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { cellValue } from './cells'
import { NEVER_SUBMIT, toPayload } from './form-payload'
import { entityLabel, enumLabel, fieldHelp, fieldLabel } from './labels'
import { RefSelect } from './ref-select'
import {
  requiredBy,
  requiredHint,
  validateDecimals,
  validateRequired,
} from './required'

type V = Record<string, unknown>

const NONE = '__none__'

function initialValues(e: MesEntity, row: MesRow | null, preset: V): V {
  const v: V = {}
  for (const f of e.fields) {
    const raw = row ? row[f.column] : (preset[f.column] ?? f.default)
    v[f.column] =
      f.type === 'json'
        ? raw == null
          ? ''
          : JSON.stringify(raw, null, 2)
        : f.type === 'time' && typeof raw === 'string'
          ? raw.slice(0, 5)
          : f.type === 'float' && raw != null && raw !== ''
            ? decimalText(raw as number | string)
            : (raw ?? (f.type === 'bool' ? false : ''))
    if (f.type === 'ref')
      v[`${f.name}_label`] = row?.[`${f.name}_label`] ?? null
  }
  v.attrs = { ...(row?.attrs ?? {}) }
  return v
}

/** 以开关渲染的布尔字段（实体.字段）；其他布尔字段仍用复选框。 */
const SWITCH_FIELDS = new Set(['qtime_rule.is_active'])
/** 编辑时只读显示的系统维护字段（实体.字段）。 */
const READONLY_ON_EDIT = new Set([
  'qtime_rule.active_since',
  // OQ-20：迁移说明只由迁移写入，表单只读展示、绝不提交（写了后端 422 read_only_field）
  'alarm_code.migration_note',
])
/** 根据实体元数据（含自定义属性）渲染的新增 / 编辑对话框。 */
export function EntityForm({
  entity: e,
  row,
  open,
  onOpenChange,
  preset = {},
  defaults = {},
  onSubmit,
  pending,
}: {
  entity: MesEntity
  row: MesRow | null
  open: boolean
  onOpenChange: (o: boolean) => void
  /** 新增行的初始值（字段仍可见） */
  defaults?: V
  /** 新增行的固定值（如父级 id），这些字段会被隐藏 */
  preset?: V
  onSubmit: (body: V) => Promise<unknown>
  pending?: boolean
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='max-h-[90vh] overflow-y-auto sm:max-w-2xl'>
        {open && (
          <FormBody
            e={e}
            row={row}
            preset={preset}
            defaults={defaults}
            onSubmit={onSubmit}
            pending={pending}
            onCancel={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function FormBody({
  e,
  row,
  preset,
  defaults,
  onSubmit,
  pending,
  onCancel,
}: {
  e: MesEntity
  row: MesRow | null
  preset: V
  defaults: V
  onSubmit: (body: V) => Promise<unknown>
  pending?: boolean
  onCancel: () => void
}) {
  const tk = useTenantKey()
  const [v, setV] = useState<V>(() =>
    initialValues(e, row, { ...defaults, ...preset })
  )
  const [jsonErr, setJsonErr] = useState<string | null>(null)
  const [errs, setErrs] = useState<Record<string, string>>({})
  const attrs = useQuery({
    queryKey: ['mes', 'attrs', e.code, tk],
    queryFn: () => mesApi.attrs(e.code),
  })
  const hidden = new Set(Object.keys(preset))
  const set = (k: string, x: unknown) => {
    setV((p) => ({ ...p, [k]: x }))
    const f = e.fields.find((y) => y.column === k)
    if (f && errs[f.name]) setErrs(({ [f.name]: _, ...rest }) => rest)
  }
  const setAttr = (k: string, x: unknown) =>
    setV((p) => ({ ...p, attrs: { ...(p.attrs as V), [k]: x } }))
  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault()
    const found = {
      ...validateDecimals(e, v, hidden),
      ...validateRequired(e, v, hidden),
    }
    setErrs(found)
    if (Object.keys(found).length) return
    let body: V
    try {
      body = toPayload(e, v, hidden)
    } catch {
      setJsonErr(t('config.invalidJson'))
      return
    }
    setJsonErr(null)
    if (!row) Object.assign(body, preset)
    await onSubmit(body)
  }
  const fields = e.fields.filter(
    (f) =>
      !hidden.has(f.column) &&
      !f.system &&
      !NEVER_SUBMIT.has(`${e.code}.${f.name}`) &&
      (!f.only_when_required || !!requiredBy(e, f, v))
  )
  // 系统维护字段编辑时只读显示（不提交）；本轮仅 Q-Time 规则的 active_since
  const readonly = row
    ? e.fields.filter(
        (f) =>
          READONLY_ON_EDIT.has(`${e.code}.${f.name}`) && row[f.column] != null
      )
    : []
  return (
    <form onSubmit={submit} noValidate className='space-y-4'>
      <DialogHeader>
        <DialogTitle>
          {t(row ? 'mes.editTitle' : 'mes.newTitle', {
            entity: entityLabel(e.code),
          })}
        </DialogTitle>
        <DialogDescription>
          {row?.version != null
            ? t('mes.versionInfo', { version: row.version })
            : t('mes.formDesc')}
        </DialogDescription>
      </DialogHeader>
      <div className='grid gap-4 sm:grid-cols-2'>
        {fields.map((f) => (
          <div
            key={f.name}
            className={
              f.type === 'text' || f.type === 'json'
                ? 'space-y-1.5 sm:col-span-2'
                : 'space-y-1.5'
            }
          >
            <Label htmlFor={`f-${f.name}`}>
              {fieldLabel(e, f)}
              {requiredBy(e, f, v) && !f.default_from && !f.auto && (
                <span className='text-destructive'> *</span>
              )}
            </Label>
            <FieldInput e={e} f={f} v={v} set={set} id={`f-${f.name}`} />
            {errs[f.name] ? (
              <p className='text-xs text-destructive' role='alert'>
                {errs[f.name]}
              </p>
            ) : (
              requiredHint(e, f, v) && (
                <p className='text-xs text-muted-foreground'>
                  {requiredHint(e, f, v)}
                </p>
              )
            )}
            {f.auto && !row && (
              <p className='text-xs text-muted-foreground'>
                {t('mes.autoHint')}
              </p>
            )}
            {f.default_from && (
              <p className='text-xs text-muted-foreground'>
                {t('mes.err.defaultsFrom', {
                  field: fieldLabel(e, f.default_from),
                })}
              </p>
            )}
            {fieldHelp(e, f) && (
              <p className='text-xs text-muted-foreground'>{fieldHelp(e, f)}</p>
            )}
          </div>
        ))}
      </div>
      {jsonErr && <p className='text-sm text-destructive'>{jsonErr}</p>}
      {readonly.length > 0 && (
        <div className='grid gap-4 sm:grid-cols-2'>
          {readonly.map((f) => (
            <div
              key={f.name}
              className='space-y-1.5'
              data-testid={`ro-${f.name}`}
            >
              <p className='text-sm font-medium'>{fieldLabel(e, f)}</p>
              <div className='text-sm text-muted-foreground'>
                {cellValue(e, row!, f.name)}
              </div>
            </div>
          ))}
        </div>
      )}
      {!!attrs.data?.length && (
        <>
          <Separator />
          <p className='text-sm font-medium'>{t('mes.customAttrs')}</p>
          <div className='grid gap-4 sm:grid-cols-2'>
            {attrs.data.map((d) => {
              const cur = (v.attrs as V)[d.code]
              return (
                <div key={d.code} className='space-y-1.5'>
                  <Label htmlFor={`a-${d.code}`}>
                    {d.name}
                    {d.required && <span className='text-destructive'> *</span>}
                  </Label>
                  {d.data_type === 'boolean' ? (
                    <Checkbox
                      id={`a-${d.code}`}
                      checked={cur === true}
                      onCheckedChange={(c) => setAttr(d.code, c === true)}
                    />
                  ) : d.data_type === 'select' ? (
                    <Select
                      value={cur ? String(cur) : NONE}
                      onValueChange={(x) =>
                        setAttr(d.code, x === NONE ? null : x)
                      }
                    >
                      <SelectTrigger id={`a-${d.code}`} className='w-full'>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={NONE}>—</SelectItem>
                        {d.options.map((o) => (
                          <SelectItem key={o} value={o}>
                            {o}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      id={`a-${d.code}`}
                      type={
                        d.data_type === 'number'
                          ? 'number'
                          : d.data_type === 'date'
                            ? 'date'
                            : 'text'
                      }
                      value={cur == null ? '' : String(cur)}
                      onChange={(ev) =>
                        setAttr(
                          d.code,
                          ev.target.value === ''
                            ? null
                            : d.data_type === 'number'
                              ? Number(ev.target.value)
                              : ev.target.value
                        )
                      }
                    />
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}
      <DialogFooter>
        <Button type='button' variant='outline' onClick={onCancel}>
          {t('common.cancel')}
        </Button>
        <Button type='submit' disabled={pending}>
          {pending && <Loader2 className='animate-spin' />}
          {t('common.save')}
        </Button>
      </DialogFooter>
    </form>
  )
}

function FieldInput({
  e,
  f,
  v,
  set,
  id,
}: {
  e: MesEntity
  f: MesField
  v: V
  set: (k: string, x: unknown) => void
  id: string
}) {
  const val = v[f.column]
  switch (f.type) {
    case 'bool':
      return (
        <div className='flex h-9 items-center'>
          {SWITCH_FIELDS.has(`${e.code}.${f.name}`) ? (
            <Switch
              id={id}
              checked={val === true}
              onCheckedChange={(c) => set(f.column, c)}
            />
          ) : (
            <Checkbox
              id={id}
              checked={val === true}
              onCheckedChange={(c) => set(f.column, c === true)}
            />
          )}
        </div>
      )
    case 'enum':
      return (
        <EnumSelect
          id={id}
          en={f.enum!}
          value={String(val ?? '')}
          required={f.required}
          onChange={(x) => set(f.column, x)}
        />
      )
    case 'ref':
      return (
        <RefSelect
          id={id}
          target={f.ref!}
          value={(val as string) || null}
          label={v[`${f.name}_label`] as string | null}
          filters={
            f.depends || f.ref_filter
              ? {
                  ...f.ref_filter,
                  ...(f.depends
                    ? {
                        [`${f.depends}_id`]: String(v[`${f.depends}_id`] ?? ''),
                      }
                    : {}),
                }
              : undefined
          }
          disabled={!!f.depends && !v[`${f.depends}_id`]}
          onChange={(rid, lbl) => {
            set(f.column, rid ?? '')
            set(`${f.name}_label`, lbl)
          }}
        />
      )
    case 'text':
    case 'json':
      return (
        <Textarea
          id={id}
          rows={f.type === 'json' ? 4 : 2}
          className={f.type === 'json' ? 'font-mono text-xs' : undefined}
          value={String(val ?? '')}
          onChange={(ev) => set(f.column, ev.target.value)}
        />
      )
    default:
      return (
        <Input
          id={id}
          type={
            f.type === 'int' || f.type === 'float'
              ? 'number'
              : f.type === 'date'
                ? 'date'
                : f.type === 'time'
                  ? 'time'
                  : 'text'
          }
          step={f.type === 'float' ? 'any' : undefined}
          maxLength={f.max_length ?? undefined}
          required={f.required}
          value={String(val ?? '')}
          onChange={(ev) => set(f.column, ev.target.value)}
          aria-label={fieldLabel(e, f)}
        />
      )
  }
}

/** 枚举下拉（选项标签按当前语言翻译）。 */
export function EnumSelect({
  en,
  value,
  onChange,
  required,
  id,
}: {
  en: string
  value: string
  onChange: (v: string) => void
  required?: boolean
  id?: string
}) {
  const { data } = useQuery({
    queryKey: ['mes', 'meta-enums'],
    queryFn: mesApi.meta,
    staleTime: Infinity,
    select: (m) => m.enums[en] ?? [],
  })
  return (
    <Select
      value={value || NONE}
      onValueChange={(x) => onChange(x === NONE ? '' : x)}
    >
      <SelectTrigger id={id} className='w-full'>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {!required && <SelectItem value={NONE}>—</SelectItem>}
        {(data ?? []).map((o) => (
          <SelectItem key={o} value={o}>
            {enumLabel(en, o)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
