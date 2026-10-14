/** 系统配置项输入控件。 */
import { useRef, useState } from 'react'
import { t } from '@/i18n'
import { ImageIcon, Loader2, Trash2, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { api, type ConfigItem } from '@/lib/api'
import { errorMessage } from '@/lib/api/client'
import { assetUrl } from '@/lib/branding'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'

const IMAGE_ACCEPT =
  'image/png,image/jpeg,image/svg+xml,image/webp,image/x-icon,.ico'

/** 按 value_type 渲染的输入控件；JSON 配置以文本编辑（`value` 为字符串）。 */
export function ConfigField({
  item,
  value,
  onChange,
  scope,
  id,
  error,
}: {
  item: ConfigItem
  value: unknown
  onChange: (v: unknown) => void
  scope: 'tenant' | 'platform'
  id: string
  error?: string
}) {
  const s = typeof value === 'string' ? value : ''
  const invalid = error ? { 'aria-invalid': true } : {}
  switch (item.value_type) {
    case 'text':
      return (
        <Textarea
          id={id}
          value={s}
          rows={3}
          onChange={(e) => onChange(e.target.value)}
          {...invalid}
        />
      )
    case 'json':
      return (
        <Textarea
          id={id}
          value={s}
          rows={5}
          className='font-mono text-xs'
          spellCheck={false}
          onChange={(e) => onChange(e.target.value)}
          {...invalid}
        />
      )
    case 'number':
      return (
        <Input
          id={id}
          type='number'
          className='max-w-48'
          value={typeof value === 'number' ? value : ''}
          min={item.validation?.min as number | undefined}
          max={item.validation?.max as number | undefined}
          onChange={(e) =>
            onChange(e.target.value === '' ? null : Number(e.target.value))
          }
          {...invalid}
        />
      )
    case 'boolean':
      return (
        <Switch
          id={id}
          checked={value === true}
          onCheckedChange={(c) => onChange(c)}
        />
      )
    case 'select':
      return (
        <Select value={s} onValueChange={onChange}>
          <SelectTrigger id={id} className='max-w-full min-w-64'>
            <SelectValue placeholder={t('common.select')} />
          </SelectTrigger>
          <SelectContent>
            {(item.options ?? []).map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )
    case 'color':
      return (
        <div className='flex items-center gap-2'>
          <input
            type='color'
            aria-label={item.name}
            value={/^#[0-9a-f]{6}$/i.test(s) ? s : '#000000'}
            onChange={(e) => onChange(e.target.value)}
            className='h-9 w-12 cursor-pointer rounded-md border bg-transparent p-1'
          />
          <Input
            id={id}
            value={s}
            className='w-32 font-mono'
            placeholder='#1e40af'
            onChange={(e) => onChange(e.target.value)}
            {...invalid}
          />
        </div>
      )
    case 'url':
      return (
        <Input
          id={id}
          type='url'
          value={s}
          placeholder='https://'
          onChange={(e) => onChange(e.target.value)}
          {...invalid}
        />
      )
    case 'image':
    case 'file':
      return <ImageField id={id} value={s} onChange={onChange} scope={scope} />
    default:
      return (
        <Input
          id={id}
          value={s}
          maxLength={item.validation?.max_length as number | undefined}
          onChange={(e) => onChange(e.target.value)}
          {...invalid}
        />
      )
  }
}

function ImageField({
  id,
  value,
  onChange,
  scope,
}: {
  id: string
  value: string
  onChange: (v: unknown) => void
  scope: 'tenant' | 'platform'
}) {
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const src = assetUrl(value)
  const upload = async (file: File | undefined) => {
    if (!file) return
    setBusy(true)
    try {
      const res = await api.files.upload(file, scope)
      onChange(res.url)
      toast.success(t('config.uploaded'))
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }
  return (
    <div className='flex items-center gap-3'>
      <div className='flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-muted/40'>
        {src ? (
          <img src={src} alt='' className='size-full object-contain' />
        ) : (
          <ImageIcon className='size-6 text-muted-foreground' />
        )}
      </div>
      <input
        ref={input}
        id={id}
        type='file'
        accept={IMAGE_ACCEPT}
        className='hidden'
        onChange={(e) => upload(e.target.files?.[0])}
      />
      <Button
        type='button'
        variant='outline'
        size='sm'
        disabled={busy}
        onClick={() => input.current?.click()}
      >
        {busy ? <Loader2 className='animate-spin' /> : <Upload />}
        {src ? t('config.replace') : t('config.upload')}
      </Button>
      {src && (
        <Button
          type='button'
          variant='ghost'
          size='sm'
          onClick={() => onChange('')}
        >
          <Trash2 />
          {t('config.remove')}
        </Button>
      )}
      <span className='text-xs text-muted-foreground'>
        {t('config.imageHint')}
      </span>
    </div>
  )
}
