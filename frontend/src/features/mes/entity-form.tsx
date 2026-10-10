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
} from '@/lib/api/mes'
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
import { Textarea } from '@/components/ui/textarea'
import { entityLabel, enumLabel, fieldHelp, fieldLabel } from './labels'
import { RefSelect } from './ref-select'

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
          : (raw ?? (f.type === 'bool' ? false : ''))
    if (f.type === 'ref')
      v[`${f.name}_label`] = row?.[`${f.name}_label`] ?? null
  }
  v.attrs = { ...(row?.attrs ?? {}) }
  return v
}

function toPayload(e: MesEntity, v: V, hidden: Set<string>): V {
  const out: V = {}
  for (const f of e.fields) {
    if (hidden.has(f.column) && v[f.column] === '') continue
    const x = v[f.column]
    if (f.type === 'json') {
      out[f.column] = x === '' ? null : JSON.parse(String(x))
    } else if (f.type === 'int' || f.type === 'float') {
      out[f.column] = x === '' || x == null ? null : Number(x)
    } else if (f.type === 'bool') {
      out[f.column] = !!x
    } else {
      out[f.column] = x === '' ? null : x
    }
  }
  out.attrs = v.attrs
  return out
}

/** Create/edit dialog rendered from entity metadata (+ custom attributes). */
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
  /** initial values for new rows (fields stay visible) */
  defaults?: V
  /** fixed values (e.g. parent id) for new rows; those fields are hidden */
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
  const attrs = useQuery({
    queryKey: ['mes', 'attrs', e.code, tk],
    queryFn: () => mesApi.attrs(e.code),
  })
  const hidden = new Set(Object.keys(preset))
  const set = (k: string, x: unknown) => setV((p) => ({ ...p, [k]: x }))
  const setAttr = (k: string, x: unknown) =>
    setV((p) => ({ ...p, attrs: { ...(p.attrs as V), [k]: x } }))
  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault()
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
  const fields = e.fields.filter((f) => !hidden.has(f.column))
  return (
    <form onSubmit={submit} className='space-y-4'>
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
              {f.required && <span className='text-destructive'> *</span>}
            </Label>
            <FieldInput e={e} f={f} v={v} set={set} id={`f-${f.name}`} />
            {fieldHelp(e, f) && (
              <p className='text-xs text-muted-foreground'>{fieldHelp(e, f)}</p>
            )}
          </div>
        ))}
      </div>
      {jsonErr && <p className='text-sm text-destructive'>{jsonErr}</p>}
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
          <Checkbox
            id={id}
            checked={val === true}
            onCheckedChange={(c) => set(f.column, c === true)}
          />
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
