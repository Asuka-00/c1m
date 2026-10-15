import { useEffect } from 'react'
import { Outlet } from '@tanstack/react-router'
import { useCurrentTenant } from '@/lib/api/hooks'
import { rememberBrandTenant, useBranding } from '@/lib/branding'
import { getCookie } from '@/lib/cookies'
import { cn } from '@/lib/utils'
import { LayoutProvider } from '@/context/layout-provider'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import { BrandFooter, BrandingHead } from '@/components/branding/branding'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { SkipToMain } from '@/components/skip-to-main'

type AuthenticatedLayoutProps = {
  children?: React.ReactNode
}

/** 登录后的应用布局：侧栏 + 内容区，应用当前租户品牌。 */
export function AuthenticatedLayout({ children }: AuthenticatedLayoutProps) {
  const defaultOpen = getCookie('sidebar_state') !== 'false'
  // 当前租户的品牌（随租户切换器变化）
  const slug = useCurrentTenant()?.tenant.slug
  const branding = useBranding(slug)
  useEffect(() => rememberBrandTenant(slug), [slug])
  return (
    <LayoutProvider>
      <SidebarProvider defaultOpen={defaultOpen}>
        <BrandingHead branding={branding} />
        <SkipToMain />
        <AppSidebar />
        <SidebarInset
          className={cn(
            // 设为内容容器，以便使用容器查询
            '@container/content',

            // 固定布局时设置高度
            // 为 100svh，防止溢出
            'has-data-[layout=fixed]:h-svh',

            // 固定布局且侧栏为 inset 时，
            // 高度设为 100svh 减去间距（总外边距），防止溢出
            'peer-data-[variant=inset]:has-data-[layout=fixed]:h-[calc(100svh-(var(--spacing)*4))]'
          )}
        >
          <div className='flex min-h-0 flex-1 flex-col'>
            {children ?? <Outlet />}
          </div>
          <BrandFooter branding={branding} className='border-t' />
        </SidebarInset>
      </SidebarProvider>
    </LayoutProvider>
  )
}
