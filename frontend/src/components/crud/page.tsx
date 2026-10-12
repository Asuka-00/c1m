import { LanguageSwitch } from '@/components/language-switch'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { NotificationBell } from '@/components/notify/notification-bell'
import { ThemeSwitch } from '@/components/theme-switch'

/** 标准页面骨架：头部（标题、说明、操作按钮）+ 主内容区。 */
export function Page({
  title,
  description,
  actions,
  children,
}: {
  title: string
  description?: React.ReactNode
  actions?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <>
      <Header fixed>
        <div className='ms-auto flex items-center gap-2'>
          <NotificationBell />
          <LanguageSwitch />
          <ThemeSwitch />
        </div>
      </Header>
      <Main className='flex flex-col gap-4'>
        <div className='flex flex-wrap items-end justify-between gap-2'>
          <div>
            <h2 className='text-2xl font-bold tracking-tight'>{title}</h2>
            {description && (
              <p className='text-muted-foreground'>{description}</p>
            )}
          </div>
          <div className='flex gap-2'>{actions}</div>
        </div>
        {children}
      </Main>
    </>
  )
}
