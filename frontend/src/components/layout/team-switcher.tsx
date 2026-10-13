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

/** 租户切换器：列出 GET /tenants/me，所选租户作为 X-Tenant-ID 发送。 */
export function TeamSwitcher() {
  const { isMobile } = useSidebar()
  const { data } = useMyTenants()
  const current = useCurrentTenant()
  // 头部显示当前租户的品牌（应用名 + Logo）
  const branding = useBranding(current?.tenant.slug)
  const setTenantId = useAuthStore((s) => s.setTenantId)
  const impersonating = useAuthStore((s) => s.impersonating)
  const setImpersonating = useAuthStore((s) => s.setImpersonating)
  const tenantId = useAuthStore((s) => s.tenantId)
  // 超级用户以非成员租户身份进入时，租户不在 /tenants/me 中
  const imp = !current && impersonating?.id === tenantId ? impersonating : null
  const qc = useQueryClient()
  const navigate = useNavigate()

  const switchTo = (id: string) => {
    setTenantId(id)
    setImpersonating(null)
    // 所有租户范围的数据都需重新获取（菜单、成员、角色等）
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
                    : imp
                      ? `${imp.name} · ${t('nav.impersonatingShort')}`
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
