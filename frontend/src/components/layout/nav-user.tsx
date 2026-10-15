import { Link } from '@tanstack/react-router'
import { t } from '@/i18n'
import {
  ArrowLeftToLine,
  ChevronsUpDown,
  LogOut,
  ShieldCheck,
  UserCog,
} from 'lucide-react'
import { useMe, usePlatformEntry, useSpace } from '@/lib/api/hooks'
import useDialogState from '@/hooks/use-dialog-state'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from '@/components/ui/sidebar'
import { SignOutDialog } from '@/components/sign-out-dialog'

const initials = (s: string) =>
  s
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((x) => x[0]!.toUpperCase())
    .join('')

/** 侧栏底部用户信息（来自 /users/me）。
 *  超级用户或持有平台权限的用户在此进入"平台管理"控制台，或从控制台"返回工作区"。 */
export function NavUser() {
  const { isMobile } = useSidebar()
  const space = useSpace()
  const [open, setOpen] = useDialogState()
  const { data: me } = useMe()
  const entry = usePlatformEntry()
  const name = me?.full_name || me?.username || '…'
  const email = me?.email ?? me?.username ?? ''
  const who = (
    <>
      <Avatar className='h-8 w-8 rounded-lg'>
        <AvatarFallback className='rounded-lg'>
          {initials(me?.full_name || email || '?')}
        </AvatarFallback>
      </Avatar>
      <div className='grid flex-1 text-start text-sm leading-tight'>
        <span
          className='truncate font-semibold'
          title={me?.is_superuser ? `${name} ${t('nav.superuserTag')}` : name}
        >
          {name}
          {me?.is_superuser && (
            <span className='ms-1 text-xs text-muted-foreground'>
              {t('nav.superuserTag')}
            </span>
          )}
        </span>
        <span className='truncate text-xs' title={email}>
          {email}
        </span>
      </div>
    </>
  )
  return (
    <>
      <SidebarMenu>
        <SidebarMenuItem>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <SidebarMenuButton
                size='lg'
                className='data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground'
              >
                {who}
                <ChevronsUpDown className='ms-auto size-4' />
              </SidebarMenuButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              className='w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg'
              side={isMobile ? 'bottom' : 'right'}
              align='end'
              sideOffset={4}
            >
              <DropdownMenuLabel className='p-0 font-normal'>
                <div className='flex items-center gap-2 px-1 py-1.5 text-start text-sm'>
                  {who}
                </div>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              {(space === 'platform' || entry) &&
                (space === 'platform' ? (
                  <DropdownMenuItem asChild>
                    <Link to='/' data-testid='back-to-workspace'>
                      <ArrowLeftToLine />
                      {t('nav.backToWorkspace')}
                    </Link>
                  </DropdownMenuItem>
                ) : (
                  <DropdownMenuItem asChild>
                    <Link
                      to='/$'
                      params={{ _splat: (entry ?? '/platform').slice(1) }}
                      data-testid='platform-entry'
                    >
                      <ShieldCheck />
                      {t('nav.platformAdmin')}
                    </Link>
                  </DropdownMenuItem>
                ))}
              <DropdownMenuItem asChild>
                <Link to='/$' params={{ _splat: 'settings' }}>
                  <UserCog />
                  {t('nav.profile')}
                </Link>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                variant='destructive'
                onClick={() => setOpen(true)}
              >
                <LogOut />
                {t('nav.signOut')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </SidebarMenuItem>
      </SidebarMenu>
      <SignOutDialog open={!!open} onOpenChange={setOpen} />
    </>
  )
}
