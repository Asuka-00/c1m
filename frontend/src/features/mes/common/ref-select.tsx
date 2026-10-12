/** MES 引用字段选择器。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Check, ChevronsUpDown, X } from 'lucide-react'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi } from '@/lib/api/mes/common'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
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
import { rowLabel } from './labels'

/** 可搜索的引用选择器（在目标实体上做服务端搜索）。 */
export function RefSelect({
  target,
  labelField = 'code',
  value,
  label,
  onChange,
  filters,
  id,
  disabled,
}: {
  target: string
  labelField?: string
  value: string | null
  /** 当前值的显示标签（来自 `<field>_label`） */
  label?: string | null
  onChange: (id: string | null, label: string | null) => void
  /** 额外的列表筛选条件，如 {route_id: '...'} */
  filters?: Record<string, string>
  id?: string
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const tk = useTenantKey()
  const { data, isFetching } = useQuery({
    queryKey: ['mes', target, 'options', tk, q, filters],
    queryFn: () =>
      mesApi.list(target, { q: q || undefined, page_size: 30, ...filters }),
    enabled: open,
  })
  return (
    <div className='flex min-w-0 gap-1'>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            id={id}
            type='button'
            variant='outline'
            role='combobox'
            disabled={disabled}
            className='min-w-0 flex-1 justify-between font-normal'
          >
            <span className={cn('truncate', !value && 'text-muted-foreground')}>
              {value ? (label ?? value) : t('common.select')}
            </span>
            <ChevronsUpDown className='opacity-50' />
          </Button>
        </PopoverTrigger>
        <PopoverContent className='w-(--radix-popover-trigger-width) p-0'>
          <Command shouldFilter={false}>
            <CommandInput
              value={q}
              onValueChange={setQ}
              placeholder={t('table.search')}
            />
            <CommandList>
              <CommandEmpty>
                {isFetching ? '…' : t('common.noResults')}
              </CommandEmpty>
              <CommandGroup>
                {(data?.data ?? []).map((r) => (
                  <CommandItem
                    key={r.id}
                    value={r.id}
                    onSelect={() => {
                      onChange(r.id, rowLabel(r, labelField))
                      setOpen(false)
                    }}
                  >
                    <Check
                      className={cn(
                        'size-4',
                        value === r.id ? 'opacity-100' : 'opacity-0'
                      )}
                    />
                    {rowLabel(r, labelField)}
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {value && !disabled && (
        <Button
          type='button'
          size='icon'
          variant='ghost'
          aria-label={t('mes.clear')}
          onClick={() => onChange(null, null)}
        >
          <X className='size-4' />
        </Button>
      )}
    </div>
  )
}
