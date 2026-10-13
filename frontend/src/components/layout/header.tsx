import { useEffect, useState } from 'react'
import { Link } from '@tanstack/react-router'
import { t } from '@/i18n'
import { ArrowLeftToLine, ShieldCheck } from 'lucide-react'
import { useSpace } from '@/lib/api/hooks'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { ImpersonationBadge } from './impersonation-badge'

type HeaderProps = React.HTMLAttributes<HTMLElement> & {
  fixed?: boolean
  ref?: React.Ref<HTMLElement>
}

/** 页面顶部栏：侧栏开关与右侧工具；滚动时显示阴影，可固定。
 *  平台管理控制台（/platform/...）使用醒目的琥珀色底色与"平台管理"徽标。 */
export function Header({ className, fixed, children, ...props }: HeaderProps) {
  const [offset, setOffset] = useState(0)
  const platform = useSpace() === 'platform'

  useEffect(() => {
    const onScroll = () => {
      setOffset(document.body.scrollTop || document.documentElement.scrollTop)
    }

    // 为 body 添加滚动监听
    document.addEventListener('scroll', onScroll, { passive: true })

    // 卸载时移除事件监听
    return () => document.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header
      className={cn(
        'z-50 h-16',
        fixed && 'header-fixed peer/header sticky top-0 w-[inherit]',
        offset > 10 && fixed ? 'shadow' : 'shadow-none',
        platform &&
          'border-b border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/60',
        className
      )}
      {...props}
    >
      <div
        className={cn(
          'relative flex h-full items-center gap-3 p-4 sm:gap-4',
          offset > 10 &&
            fixed &&
            'after:absolute after:inset-0 after:-z-10 after:bg-background/20 after:backdrop-blur-lg'
        )}
      >
        <SidebarTrigger variant='outline' className='max-md:scale-125' />
        <Separator orientation='vertical' className='h-6' />
        {platform && (
          <>
            <Badge
              data-testid='platform-badge'
              className='gap-1 bg-amber-500 text-white hover:bg-amber-500'
            >
              <ShieldCheck className='size-3' />
              {t('nav.platformAdmin')}
            </Badge>
            <Button variant='ghost' size='sm' asChild>
              <Link to='/'>
                <ArrowLeftToLine />
                <span className='max-sm:hidden'>
                  {t('nav.backToWorkspace')}
                </span>
              </Link>
            </Button>
          </>
        )}
        {!platform && <ImpersonationBadge />}
        {children}
      </div>
    </header>
  )
}
