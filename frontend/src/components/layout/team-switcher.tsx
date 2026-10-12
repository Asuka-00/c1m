import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { t } from '@/i18n'
import { Building2, Check, ChevronsUpDown } from 'lucide-react'
import { useAuthStore } from '@/stores/auth-store'
import { useCurrentTenant, useMyTenants } from '@/lib/api/hooks'
import { useBranding } from '@/lib/branding'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from '@/components/ui/sidebar'

/** Tenant switcher: lists GET /tenants/me, selection is sent as X-Tenant-ID. */
export function TeamSwitcher() {
  const { isMobile } = useSidebar()
  const { data } = useMyTenants()
  const current = useCurrentTenant()
  // header shows the current tenant's branding (app name + logo)
  const branding = useBranding(current?.tenant.slug)
  const setTenantId = useAuthStore((s) => s.setTenantId)
  const qc = useQueryClient()
  const navigate = useNavigate()

  const switchTo = (id: string) => {
    setTenantId(id)
    // everything tenant-scoped must be refetched (menus, members, roles ...)
    qc.invalidateQueries()
    navigate({ to: '/' })
  }

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              size='lg'
              data-testid='tenant-switcher'
              className='data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground'
            >
              {branding.logo ? (
                <img
                  src={branding.logo}
                  alt=''
                  className='aspect-square size-8 shrink-0 rounded-lg object-contain'
                />
              ) : (
                <div className='flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground'>
                  <Building2 className='size-4' />
                </div>
              )}
              <div className='grid flex-1 text-start text-sm leading-tight'>
                <span
                  className='truncate font-semibold'
                  data-testid='brand-name'
                >
                  {branding.appName}
                </span>
                <span className='truncate text-xs'>
                  {current
                    ? `${current.tenant.name} · ${current.roles.join(', ') || t('nav.noRole')}`
                    : t('nav.tenantsCount', { count: data?.count ?? 0 })}
                </span>
              </div>
              <ChevronsUpDown className='ms-auto' />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className='w-(--radix-dropdown-menu-trigger-width) min-w-64 rounded-lg'
            align='start'
            side={isMobile ? 'bottom' : 'right'}
            sideOffset={4}
          >
            <DropdownMenuLabel className='text-xs text-muted-foreground'>
              {t('nav.tenants')}
            </DropdownMenuLabel>
            {data?.data.map((m, i) => (
              <DropdownMenuItem
                key={m.tenant.id}
                onClick={() => switchTo(m.tenant.id)}
                className='gap-2 p-2'
              >
                <div className='flex size-6 items-center justify-center rounded-sm border'>
                  <Building2 className='size-4 shrink-0' />
                </div>
                <div className='grid flex-1 leading-tight'>
                  <span>{m.tenant.name}</span>
                  <span className='text-xs text-muted-foreground'>
                    {m.roles.join(', ') || t('nav.noRole')}
                  </span>
                </div>
                {current?.tenant.id === m.tenant.id ? (
                  <Check className='size-4' />
                ) : (
                  <DropdownMenuShortcut>{i + 1}</DropdownMenuShortcut>
                )}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
