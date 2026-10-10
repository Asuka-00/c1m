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

export function AuthenticatedLayout({ children }: AuthenticatedLayoutProps) {
  const defaultOpen = getCookie('sidebar_state') !== 'false'
  // branding of the CURRENT tenant (follows the tenant switcher)
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
            // Set content container, so we can use container queries
            '@container/content',

            // If layout is fixed, set the height
            // to 100svh to prevent overflow
            'has-data-[layout=fixed]:h-svh',

            // If layout is fixed and sidebar is inset,
            // set the height to 100svh - spacing (total margins) to prevent overflow
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
