/** 403 页面。 */
import { useContext } from 'react'
import { PageEmbedContext } from '@/components/crud/page-embed'
import { LanguageSwitch } from '@/components/language-switch'
import { Header } from '@/components/layout/header'
import { NotificationBell } from '@/components/notify/notification-bell'
import { ThemeSwitch } from '@/components/theme-switch'
import { ErrorPage } from './error-page'

/**
 * 403 无权限页面。
 *
 * `inApp`：在登录后的布局内（动态菜单页 / 页签 / 树页）显示时带顶栏（侧栏开关、面包屑、菜单搜索），
 * 与普通页面一致，用户可以直接换到别的菜单（FE-02）；嵌在页签里时只显示内容。
 * 独立路由 `/403`（不在侧栏布局内）不带顶栏。
 */
export function ForbiddenError({ inApp = false }: { inApp?: boolean }) {
  const embedded = useContext(PageEmbedContext)
  if (!inApp || embedded) return <ErrorPage code={403} fullHeight={!inApp} />
  return (
    <>
      <Header fixed data-testid='forbidden-header'>
        <div className='ms-auto flex items-center gap-2'>
          <NotificationBell />
          <LanguageSwitch />
          <ThemeSwitch />
        </div>
      </Header>
      <ErrorPage code={403} fullHeight={false} />
    </>
  )
}
