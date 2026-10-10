import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Search, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { type FilterDef, SEARCH_DEBOUNCE_MS } from './filter-defs'
import type { ListParams } from './use-list-params'

export function FilterToolbar({
  filters,
  params,
  children,
}: {
  filters: FilterDef[]
  params: ListParams
  children?: React.ReactNode
}) {
  if (!filters.length && !children) return null
  return (
    <div className='flex flex-wrap items-center gap-2' role='search'>
      {filters.map((f) =>
        f.type === 'text' ? (
          <TextFilter key={f.name} def={f} params={params} />
        ) : (
          <SelectFilter key={f.name} def={f} params={params} />
        )
      )}
      {children}
      {Object.keys(params.filters).length > 1 && (
        <Button
          variant='ghost'
          size='sm'
          onClick={() => filters.forEach((f) => params.setFilter(f.name, ''))}
        >
          {t('table.resetFilters')}
        </Button>
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
  // keep the box in sync when the URL changes elsewhere (back/forward, reset)
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

const ALL = '__all__'

function SelectFilter({
  def,
  params,
}: {
  def: Extract<FilterDef, { type: 'select' }>
  params: ListParams
}) {
  // the caller-supplied key identifies loadOptions
  // eslint-disable-next-line @tanstack/query/exhaustive-deps
  const loaded = useQuery({
    queryKey: def.optionsKey ?? ['filter-options', def.name],
    queryFn: () => def.loadOptions!(),
    enabled: !!def.loadOptions,
    staleTime: 60_000,
  })
  const options = def.options ?? loaded.data ?? []
  const value = params.filters[def.name] ?? ALL
  return (
    <Select
      value={value}
      onValueChange={(v) => params.setFilter(def.name, v === ALL ? '' : v)}
    >
      <SelectTrigger
        className='h-9 w-auto min-w-36'
        aria-label={def.label}
        data-filter={def.name}
      >
        <SelectValue placeholder={def.label} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{def.label}</SelectItem>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
