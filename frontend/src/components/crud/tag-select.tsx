/** 标签式多选（下拉 + 可搜索 + 已选标签可移除）。 */
import { useState } from 'react'
import { t } from '@/i18n'
import { Check, ChevronsUpDown, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'

/** 标签式多选输入：已选项显示为可移除的标签，点击展开可搜索的选项列表。 */
export function TagSelect({
  id,
  options,
  value,
  onChange,
  placeholder,
}: {
  id?: string
  options: { value: string; label: string }[]
  value: string[]
  onChange: (v: string[]) => void
  placeholder?: string
}) {
  const [open, setOpen] = useState(false)
  const label = (v: string) => options.find((o) => o.value === v)?.label ?? v
  const toggle = (v: string) =>
    onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v])
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <div
          id={id}
          role='combobox'
          aria-expanded={open}
          tabIndex={0}
          className='flex min-h-9 w-full cursor-pointer flex-wrap items-center gap-1 rounded-md border px-2 py-1 text-sm'
        >
          {value.length === 0 && (
            <span className='text-muted-foreground'>
              {placeholder ?? t('common.select')}
            </span>
          )}
          {value.map((v) => (
            <Badge key={v} variant='secondary' className='gap-1'>
              {label(v)}
              <button
                type='button'
                aria-label={t('common.remove')}
                onClick={(e) => {
                  e.stopPropagation()
                  toggle(v)
                }}
              >
                <X className='size-3' />
              </button>
            </Badge>
          ))}
          <ChevronsUpDown className='ms-auto size-4 opacity-50' />
        </div>
      </PopoverTrigger>
      <PopoverContent className='w-(--radix-popover-trigger-width) p-0'>
        <Command>
          <CommandInput placeholder={t('rbac.search')} />
          <CommandList>
            <CommandEmpty>{t('common.noResults')}</CommandEmpty>
            <CommandGroup>
              {options.map((o) => (
                <CommandItem
                  key={o.value}
                  value={o.label}
                  onSelect={() => toggle(o.value)}
                >
                  <Check
                    className={cn(
                      'size-4',
                      value.includes(o.value) ? 'opacity-100' : 'opacity-0'
                    )}
                  />
                  {o.label}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
