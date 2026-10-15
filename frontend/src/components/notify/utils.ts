/** 通知显示工具：本地化标题 / 事件名、严重度样式、关联对象跳转参数。 */
import { t } from '@/i18n'
import type { Notification, Severity } from '@/lib/api'

/** 本地化通知标题（按事件类型模板 + 参数，缺省回退存储的英文标题）。 */
export function noteTitle(n: Notification): string {
  return t(`notify.event.${n.event_type}.title`, {
    ...n.params,
    defaultValue: n.title,
  })
}

/** 本地化事件类型名称。 */
export function eventLabel(code: string, fallback?: string): string {
  return t(`notify.event.${code}.label`, { defaultValue: fallback ?? code })
}

/** 严重度对应的徽标样式。 */
export const SEVERITY_CLASS: Record<Severity, string> = {
  info: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-200',
  warning:
    'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  critical: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
}

/** 将后端链接（如 /mes/lot-console?lot=…）转换为路由跳转参数。 */
export function linkTarget(link: string) {
  const [path, qs] = link.split('?')
  const search = Object.fromEntries(new URLSearchParams(qs ?? ''))
  return {
    to: '/$' as const,
    params: { _splat: path.replace(/^\//, '') },
    search: search as never,
  }
}
