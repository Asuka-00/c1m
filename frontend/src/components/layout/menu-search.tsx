/** 全局菜单搜索（Ctrl/⌘K）：索引当前用户可见的菜单与合并菜单页签，三种语言标题与 key 均可匹配。 */
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { t } from '@/i18n'
import { Search } from 'lucide-react'
import { useMyMenus } from '@/lib/api/hooks'
import { Button } from '@/components/ui/button'
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import {
  type MenuEntry,
  matchEntries,
  menuEntries,
  menuTitle,
} from './menu-index'

const isMac = () =>
  typeof navigator !== 'undefined' &&
  /mac|iphone|ipad/i.test(navigator.platform)

/** 顶栏菜单搜索入口与对话框。 */
export function MenuSearch() {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const { data } = useMyMenus()
  const navigate = useNavigate()
  const entries = useMemo(() => menuEntries(data?.menus ?? []), [data])
  const hits = matchEntries(entries, q)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen((o) => !o)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const go = (x: MenuEntry) => {
    setOpen(false)
    setQ('')
    const search = (x.tab ? { tab: x.tab } : {}) as never
    if (x.path === '/') navigate({ to: '/', search })
    else navigate({ to: '/$', params: { _splat: x.path.slice(1) }, search })
  }

  // 按所属分组归类（保持菜单顺序）
  const groups: { key: string; title: string; items: MenuEntry[] }[] = []
  for (const x of hits) {
    const gk = x.group?.key ?? ''
    let g = groups.find((y) => y.key === gk)
    if (!g) {
      g = {
        key: gk,
        title: x.group ? menuTitle(x.group.key, x.group.title) : '',
        items: [],
      }
      groups.push(g)
    }
    g.items.push(x)
  }

  return (
    <>
      <Button
        variant='outline'
        size='sm'
        className='gap-2 text-muted-foreground'
        data-testid='menu-search-open'
        onClick={() => setOpen(true)}
      >
        <Search />
        <span className='max-sm:hidden'>{t('nav.searchMenu')}</span>
        <kbd className='rounded border px-1 font-mono text-[10px] max-sm:hidden'>
          {isMac() ? '⌘K' : 'Ctrl K'}
        </kbd>
      </Button>
      <CommandDialog
        open={open}
        onOpenChange={(o) => {
          setOpen(o)
          if (!o) setQ('')
        }}
        title={t('nav.searchMenu')}
        description={t('nav.searchMenuHint')}
        shouldFilter={false}
      >
        <CommandInput
          value={q}
          onValueChange={setQ}
          placeholder={t('nav.searchMenuHint')}
        />
        {/* 过滤由 matchEntries 完成（三语 + key），cmdk 自身不再过滤 */}
        <CommandList>
          <CommandEmpty>{t('nav.searchMenuEmpty')}</CommandEmpty>
          {groups.map((g) => (
            <CommandGroup key={g.key || '-'} heading={g.title}>
              {g.items.map((x) => (
                <CommandItem
                  key={x.id}
                  value={x.id}
                  data-testid={`menu-hit-${x.id}`}
                  onSelect={() => go(x)}
                >
                  {x.parent && (
                    <span className='text-muted-foreground'>
                      {menuTitle(x.parent.key, x.parent.title)} ›
                    </span>
                  )}
                  {menuTitle(x.key, x.fallback)}
                </CommandItem>
              ))}
            </CommandGroup>
          ))}
        </CommandList>
      </CommandDialog>
    </>
  )
}
