/** 顶栏面包屑：分组 › 菜单 › 页签（由当前路由在菜单树中反查）。 */
import { Link, useLocation } from '@tanstack/react-router'
import { t } from '@/i18n'
import { ChevronRight } from 'lucide-react'
import { useMyMenus } from '@/lib/api/hooks'
import { cn } from '@/lib/utils'
import { breadcrumbOf } from './menu-index'

export function MenuBreadcrumb() {
  const { data } = useMyMenus()
  const loc = useLocation()
  const tab = (loc.search as Record<string, unknown> | undefined)?.tab
  const crumbs = breadcrumbOf(data?.menus ?? [], loc.pathname, tab)
  if (!crumbs.length) return null
  return (
    <nav
      aria-label={t('nav.breadcrumb')}
      data-testid='breadcrumb'
      className='min-w-0 text-sm max-md:hidden'
    >
      <ol className='flex items-center gap-1 truncate text-muted-foreground'>
        {crumbs.map((c, i) => {
          const last = i === crumbs.length - 1
          return (
            <li
              key={c.key}
              className={cn(
                'flex min-w-0 items-center gap-1',
                last && 'font-medium text-foreground'
              )}
              aria-current={last ? 'page' : undefined}
            >
              {i > 0 && (
                <ChevronRight
                  className='size-3.5 shrink-0 text-muted-foreground'
                  aria-hidden='true'
                />
              )}
              <span className='truncate'>
                {!last && c.path ? (
                  c.path === '/' ? (
                    <Link to='/' className='hover:underline'>
                      {c.title}
                    </Link>
                  ) : (
                    <Link
                      to='/$'
                      params={{ _splat: c.path.slice(1) }}
                      className='hover:underline'
                    >
                      {c.title}
                    </Link>
                  )
                ) : (
                  c.title
                )}
              </span>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
