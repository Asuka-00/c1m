/** 平台管理控制台的侧栏头部：醒目的"平台管理"标识（替代租户切换器）。 */
import { Link } from '@tanstack/react-router'
import { t } from '@/i18n'
import { ShieldCheck } from 'lucide-react'
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar'

/** 平台控制台标识，点击回到控制台首页（租户列表）。 */
export function PlatformBrand() {
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <SidebarMenuButton size='lg' asChild data-testid='platform-brand'>
          <Link to='/$' params={{ _splat: 'platform/tenants' }}>
            <div className='flex aspect-square size-8 items-center justify-center rounded-lg bg-amber-500 text-white'>
              <ShieldCheck className='size-4' />
            </div>
            <div className='grid flex-1 text-start text-sm leading-tight'>
              <span className='truncate font-semibold'>
                {t('nav.platformAdmin')}
              </span>
              <span className='truncate text-xs text-muted-foreground'>
                {t('nav.platformSubtitle')}
              </span>
            </div>
          </Link>
        </SidebarMenuButton>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
