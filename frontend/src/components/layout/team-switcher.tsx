import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { t } from '@/i18n'
import { Building2, Check, ChevronsUpDown } from 'lucide-react'
import { useAuthStore } from '@/stores/auth-store'
import { api } from '@/lib/api'
import { useCurrentTenant, useMyTenants } from '@/lib/api/hooks'
import { useBranding } from '@/lib/branding'
import { roleLabel } from '@/lib/rbac-labels'
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

/** 侧栏头部：品牌（应用名 + Logo）与厂区切换。
 *
 *  工作区用户不感知多租户：只属于一个厂区（租户）时不显示切换下拉；
 *  属于多个时下拉标题为“厂区”。所选租户作为 X-Tenant-ID 发送。 */
export function TeamSwitcher() {
  const { isMobile } = useSidebar()
  const { data } = useMyTenants()
  const current = useCurrentTenant()
  // 头部显示当前租户的品牌（应用名 + Logo）
  const branding = useBranding(current?.tenant.slug)
  const setTenantId = useAuthStore((s) => s.setTenantId)
  const impersonating = useAuthStore((s) => s.impersonating)
  const endImpersonation = useAuthStore((s) => s.endImpersonation)
  const tenantId = useAuthStore((s) => s.tenantId)
  // 超级用户以非成员租户身份进入时，租户不在 /tenants/me 中
  const imp = !current && impersonating?.id === tenantId ? impersonating : null
  const qc = useQueryClient()
  const navigate = useNavigate()

  const roles = (rs: string[]) =>
    rs.map((name) => roleLabel({ name })).join(', ') || t('nav.noRole')
  // 只有一个（或没有）厂区且不在模拟身份时：仅显示品牌，不提供切换
  const switchable = !!imp || (data?.count ?? 0) > 1

  const switchTo = (id: string) => {
    if (impersonating) {
      // 切回自己的租户：先恢复原令牌并记录退出
      const imp = endImpersonation()
      if (imp) void api.platform.exitTenant(imp.id).catch(() => undefined)
    }
    setTenantId(id)
    // 所有租户范围的数据都需重新获取（菜单、成员、角色等）
    qc.invalidateQueries()
    navigate({ to: '/' })
  }

  const head = (
    <SidebarMenuButton
      size='lg'
      data-testid={switchable ? 'tenant-switcher' : 'tenant-brand'}
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
        <span className='truncate font-semibold' data-testid='brand-name'>
          {branding.appName}
        </span>
        <span className='truncate text-xs'>
          {current
            ? switchable
              ? `${current.tenant.name} · ${roles(current.roles)}`
              : roles(current.roles)
            : imp
              ? `${imp.name} · ${t('nav.impersonatingShort')}`
              : (data?.count ?? 0) === 0
                ? t('nav.noTenant')
                : t('nav.tenantsCount', { count: data?.count ?? 0 })}
        </span>
      </div>
      {switchable && <ChevronsUpDown className='ms-auto' />}
    </SidebarMenuButton>
  )

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        {!switchable ? (
          head
        ) : (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>{head}</DropdownMenuTrigger>
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
                      {roles(m.roles)}
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
        )}
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
