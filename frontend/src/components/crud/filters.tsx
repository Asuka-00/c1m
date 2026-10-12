import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import {
  CalendarDays,
  Check,
  ChevronDown,
  Search,
  SlidersHorizontal,
  X,
} from 'lucide-react'
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
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  type FilterDef,
  filterKeys,
  filterOptionsKey,
  SEARCH_DEBOUNCE_MS,
  ymd,
} from './filter-defs'
import type { ListParams } from './use-list-params'

/** 默认直接显示的下拉 / 日期筛选个数，其余收进“更多筛选”。 */
export const VISIBLE_FILTERS = 4

/**
 * 表格筛选工具栏：关键字搜索 + 常用筛选直接显示，其余收进“更多筛选”（显示已生效数量），
 * 提供重置按钮；从关联对象链接跳转（?id=）时显示可移除的“指定记录”标记。
 */
export function FilterToolbar({
  filters,
  params,
  children,
}: {
  filters: FilterDef[]
  params: ListParams
  children?: React.ReactNode
}) {
  const [more, setMore] = useState(false)
  if (!filters.length && !children) return null
  const text = filters.filter((f) => f.type === 'text')
  const rest = filters.filter((f) => f.type !== 'text')
  const shown = rest.slice(0, VISIBLE_FILTERS)
  const hidden = rest.slice(VISIBLE_FILTERS)
  const hiddenActive = hidden.filter((f) =>
    filterKeys(f).some((k) => params.filters[k])
  ).length
  const resetAll = () =>
    ['id', ...filters.flatMap(filterKeys)].forEach((k) =>
      params.setFilter(k, '')
    )
  const render = (f: FilterDef) =>
    f.type === 'text' ? (
      <TextFilter key={f.name} def={f} params={params} />
    ) : f.type === 'daterange' ? (
      <DateRangeFilter key={f.name} def={f} params={params} />
    ) : (
      <SelectFilter key={f.name} def={f} params={params} />
    )
  return (
    <div className='flex flex-col gap-2' role='search'>
      <div className='flex flex-wrap items-center gap-2'>
        {text.map(render)}
        {shown.map(render)}
        {hidden.length > 0 && (
          <Button
            variant='outline'
            size='sm'
            className='h-9'
            onClick={() => setMore((m) => !m)}
            aria-expanded={more}
            data-testid='more-filters'
          >
            <SlidersHorizontal />
            {t('table.moreFilters')}
            {hiddenActive > 0 && (
              <span className='rounded-full bg-primary px-1.5 text-[10px] text-primary-foreground'>
                {hiddenActive}
              </span>
            )}
          </Button>
        )}
        {params.filters.id && (
          <Button
            variant='secondary'
            size='sm'
            className='h-9'
            onClick={() => params.setFilter('id', '')}
            title={t('table.clearRecordFilter')}
          >
            {t('table.recordFilter')}
            <X />
          </Button>
        )}
        {children}
        {Object.keys(params.filters).length > 1 && (
          <Button variant='ghost' size='sm' onClick={resetAll}>
            {t('table.resetFilters')}
          </Button>
        )}
      </div>
      {more && hidden.length > 0 && (
        <div
          className='flex flex-wrap items-center gap-2 rounded-md border border-dashed p-2'
          data-testid='more-filters-panel'
        >
          {hidden.map(render)}
        </div>
      )}
    </div>
  )
}

function TextFilter({
  def,
  params,
}: {
  def: Extract<FilterDef, { type: 'text' }>
  params: ListParams
}) {
  const current = params.filters[def.name] ?? ''
  const [value, setValue] = useState(current)
  // URL 在别处变化时（前进 / 后退、重置）同步输入框
  const [synced, setSynced] = useState(current)
  if (current !== synced) {
    setSynced(current)
    setValue(current)
  }
  const { setFilter } = params
  useEffect(() => {
    if (value.trim() === current) return
    const id = setTimeout(
      () => setFilter(def.name, value.trim()),
      SEARCH_DEBOUNCE_MS
    )
    return () => clearTimeout(id)
  }, [value, current, def.name, setFilter])
  const clear = () => {
    setValue('')
    params.setFilter(def.name, '')
  }
  const placeholder = def.placeholder ?? t('table.search')
  return (
    <div className='relative w-full max-w-xs'>
      <Search className='pointer-events-none absolute start-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground' />
      <Input
        type='search'
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === 'Escape' && value && clear()}
        placeholder={placeholder}
        aria-label={placeholder}
        className='h-9 ps-8 pe-8 [&::-webkit-search-cancel-button]:hidden'
      />
      {value && (
        <Button
          variant='ghost'
          size='icon'
          className='absolute end-0.5 top-1/2 size-8 -translate-y-1/2'
          onClick={clear}
          aria-label={t('table.clearSearch')}
        >
          <X className='size-4' />
        </Button>
      )}
    </div>
  )
}

/** 下拉筛选：可输入关键字过滤选项；配置 `search` 时为远程搜索（大数据量引用字段）。 */
function SelectFilter({
  def,
  params,
}: {
  def: Extract<FilterDef, { type: 'select' }>
  params: ListParams
}) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [dq, setDq] = useState('')
  useEffect(() => {
    const id = setTimeout(() => setDq(q.trim()), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(id)
  }, [q])
  const remote = !!def.search
  // 由调用方提供的 key 标识 loadOptions
  const loaded = useQuery({
    queryKey: filterOptionsKey(def),
    queryFn: () => def.loadOptions!(),
    enabled: !!def.loadOptions && !remote,
    staleTime: 60_000,
  })
  const found = useQuery({
    queryKey: [...filterOptionsKey(def), 'search', dq],
    queryFn: () => def.search!(dq),
    enabled: remote && open,
    staleTime: 30_000,
  })
  const value = params.filters[def.name] ?? ''
  const options = remote
    ? (found.data ?? [])
    : (def.options ?? (Array.isArray(loaded.data) ? loaded.data : []))
  const resolved = useQuery({
    queryKey: [...filterOptionsKey(def), 'label', value],
    queryFn: () => def.resolve!(value),
    enabled: remote && !!value && !!def.resolve,
    staleTime: 5 * 60_000,
  })
  const current =
    options.find((o) => o.value === value)?.label ??
    (remote ? resolved.data : undefined) ??
    (value || '')
  const pick = (v: string) => {
    params.setFilter(def.name, v)
    setOpen(false)
    setQ('')
  }
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant='outline'
          role='combobox'
          aria-expanded={open}
          aria-label={def.label}
          data-filter={def.name}
          className={cn(
            'h-9 w-auto max-w-64 min-w-36 justify-between font-normal',
            !value && 'text-muted-foreground'
          )}
        >
          <span className='truncate'>{value ? current : def.label}</span>
          <ChevronDown className='size-4 opacity-50' />
        </Button>
      </PopoverTrigger>
      <PopoverContent className='w-72 p-0' align='start'>
        <Command shouldFilter={!remote}>
          <CommandInput
            value={q}
            onValueChange={setQ}
            placeholder={t('table.searchOptions')}
          />
          <CommandList>
            <CommandEmpty>
              {found.isFetching ? '…' : t('common.noResults')}
            </CommandEmpty>
            <CommandGroup>
              {!q && (
                <CommandItem
                  value={`__all__ ${def.label}`}
                  onSelect={() => pick('')}
                >
                  <Check className={cn('size-4', value ? 'opacity-0' : '')} />
                  {def.label}
                </CommandItem>
              )}
              {options.map((o) => (
                <CommandItem
                  key={o.value}
                  value={`${o.label} ${o.value}`}
                  onSelect={() => pick(o.value)}
                >
                  <Check
                    className={cn(
                      'size-4',
                      o.value === value ? '' : 'opacity-0'
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

/** 日期范围筛选：快捷区间（今天 / 近 7 天 / 近 30 天 / 本月）+ 自定义起止日期。 */
function DateRangeFilter({
  def,
  params,
}: {
  def: Extract<FilterDef, { type: 'daterange' }>
  params: ListParams
}) {
  const [kf, kt] = filterKeys(def)
  const from = params.filters[kf] ?? ''
  const to = params.filters[kt] ?? ''
  const setRange = (a: string, b: string) => {
    params.setRange(kf, a, kt, b)
  }
  const today = new Date()
  const back = (n: number) =>
    ymd(new Date(today.getFullYear(), today.getMonth(), today.getDate() - n))
  const presets: [string, string, string][] = [
    [t('table.range.today'), ymd(today), ymd(today)],
    [t('table.range.last7'), back(6), ymd(today)],
    [t('table.range.last30'), back(29), ymd(today)],
    [
      t('table.range.thisMonth'),
      ymd(new Date(today.getFullYear(), today.getMonth(), 1)),
      ymd(today),
    ],
  ]
  const active = from || to
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant='outline'
          aria-label={def.label}
          data-filter={def.name}
          className={cn(
            'h-9 w-auto min-w-36 justify-between font-normal',
            !active && 'text-muted-foreground'
          )}
        >
          <CalendarDays className='size-4 opacity-60' />
          <span className='truncate'>
            {active ? `${def.label}：${from || '…'} ~ ${to || '…'}` : def.label}
          </span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className='w-80' align='start'>
        <div className='flex flex-col gap-3'>
          <div className='flex flex-wrap gap-1'>
            {presets.map(([l, a, b]) => (
              <Button
                key={l}
                size='sm'
                variant={from === a && to === b ? 'default' : 'outline'}
                onClick={() => setRange(a, b)}
              >
                {l}
              </Button>
            ))}
          </div>
          <div className='flex items-center gap-2'>
            <Input
              type='date'
              value={from}
              max={to || undefined}
              aria-label={t('table.range.from')}
              onChange={(e) => setRange(e.target.value, to)}
            />
            <span>~</span>
            <Input
              type='date'
              value={to}
              min={from || undefined}
              aria-label={t('table.range.to')}
              onChange={(e) => setRange(from, e.target.value)}
            />
          </div>
          {active && (
            <Button variant='ghost' size='sm' onClick={() => setRange('', '')}>
              {t('table.range.clear')}
            </Button>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
