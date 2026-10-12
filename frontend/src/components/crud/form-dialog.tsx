import { useState } from 'react'
import { t } from '@/i18n'
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
import { Textarea } from '@/components/ui/textarea'

/** 表单字段值。 */
export type FieldValue = string | boolean | string[]
/** 表单值：字段名 -> 值。 */
export type Values = Record<string, FieldValue>

/** FormDialog 的字段定义（类型、标签、必填、选项等）。 */
export interface Field {
  name: string
  label: string
  type?:
    | 'text'
    | 'email'
    | 'password'
    | 'textarea'
    | 'checkbox'
    | 'select'
    | 'multi'
    | 'number'
  options?: { value: string; label: string }[]
  required?: boolean
  placeholder?: string
  hidden?: boolean
}

/** 由字段列表驱动的通用新增 / 编辑对话框。 */
export function FormDialog({
  open,
  onOpenChange,
  title,
  description,
  fields,
  initial,
  onSubmit,
  pending,
  submitText = t('common.save'),
}: {
  open: boolean
  onOpenChange: (o: boolean) => void
  title: string
  description?: string
  fields: Field[]
  initial: Values
  onSubmit: (v: Values) => Promise<unknown> | void
  pending?: boolean
  submitText?: string
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        {open && (
          <FormBody
            title={title}
            description={description}
            fields={fields}
            initial={initial}
            onSubmit={onSubmit}
            onOpenChange={onOpenChange}
            pending={pending}
            submitText={submitText}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function FormBody({
  title,
  description,
  fields,
  initial,
  onSubmit,
  onOpenChange,
  pending,
  submitText,
}: {
  title: string
  description?: string
  fields: Field[]
  initial: Values
  onSubmit: (v: Values) => Promise<unknown> | void
  onOpenChange: (o: boolean) => void
  pending?: boolean
  submitText: string
}) {
  const [values, setValues] = useState<Values>(initial)
  const set = (k: string, v: FieldValue) => setValues((s) => ({ ...s, [k]: v }))
  return (
    <>
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        {description && <DialogDescription>{description}</DialogDescription>}
      </DialogHeader>
      <form
        id='crud-form'
        className='grid gap-4'
        onSubmit={async (e) => {
          e.preventDefault()
          try {
            await onSubmit(values)
            onOpenChange(false)
          } catch {
            /* error toast shown by mutation */
          }
        }}
      >
        {fields
          .filter((f) => !f.hidden)
          .map((f) => {
            const v = values[f.name]
            if (f.type === 'checkbox')
              return (
                <div key={f.name} className='flex items-center gap-2'>
                  <Checkbox
                    id={f.name}
                    checked={!!v}
                    onCheckedChange={(c) => set(f.name, !!c)}
                  />
                  <Label htmlFor={f.name}>{f.label}</Label>
                </div>
              )
            return (
              <div key={f.name} className='grid gap-2'>
                <Label htmlFor={f.name}>{f.label}</Label>
                {f.type === 'textarea' ? (
                  <Textarea
                    id={f.name}
                    value={(v as string) ?? ''}
                    onChange={(e) => set(f.name, e.target.value)}
                  />
                ) : f.type === 'select' ? (
                  <Select
                    value={(v as string) || undefined}
                    onValueChange={(x) => set(f.name, x)}
                  >
                    <SelectTrigger id={f.name} className='w-full'>
                      <SelectValue
                        placeholder={f.placeholder ?? t('common.select')}
                      />
                    </SelectTrigger>
                    <SelectContent>
                      {f.options?.map((o) => (
                        <SelectItem key={o.value} value={o.value}>
                          {o.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : f.type === 'multi' ? (
                  <div className='flex flex-wrap gap-3 rounded-md border p-3'>
                    {f.options?.map((o) => {
                      const arr = (v as string[]) ?? []
                      return (
                        <label
                          key={o.value}
                          className='flex items-center gap-2 text-sm'
                        >
                          <Checkbox
                            checked={arr.includes(o.value)}
                            onCheckedChange={(c) =>
                              set(
                                f.name,
                                c
                                  ? [...arr, o.value]
                                  : arr.filter((x) => x !== o.value)
                              )
                            }
                          />
                          {o.label}
                        </label>
                      )
                    })}
                  </div>
                ) : (
                  <Input
                    id={f.name}
                    type={f.type ?? 'text'}
                    required={f.required}
                    placeholder={f.placeholder}
                    value={(v as string) ?? ''}
                    onChange={(e) => set(f.name, e.target.value)}
                  />
                )}
              </div>
            )
          })}
      </form>
      <DialogFooter>
        <Button variant='outline' onClick={() => onOpenChange(false)}>
          {t('common.cancel')}
        </Button>
        <Button type='submit' form='crud-form' disabled={pending}>
          {submitText}
        </Button>
      </DialogFooter>
    </>
  )
}
