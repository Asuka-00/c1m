/** 顶栏面包屑：分组 › 菜单 › 页签（由当前路由在菜单树中反查）。 */
import { Fragment } from 'react'
import { Link, useLocation } from '@tanstack/react-router'
import { t } from '@/i18n'
import { ChevronRight } from 'lucide-react'
import { useMyMenus } from '@/lib/api/hooks'
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
            <Fragment key={c.key}>
              {i > 0 && <ChevronRight className='size-3.5 shrink-0' />}
              <li
                className={
                  last ? 'truncate font-medium text-foreground' : 'truncate'
                }
                aria-current={last ? 'page' : undefined}
              >
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
              </li>
            </Fragment>
          )
        })}
      </ol>
    </nav>
  )
}
