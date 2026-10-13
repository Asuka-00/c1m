/** 引用字段的关联对象链接。 */
import { Link } from '@tanstack/react-router'
import type { MenuNode } from '@/lib/api'
import { useMyMenus } from '@/lib/api/hooks'
import { cn } from '@/lib/utils'
import { resolveRedirect } from '@/features/shell/dynamic/merged'
import { useMesMeta } from './use-mes-meta'

const paths = (ns: MenuNode[]): string[] =>
  ns.flatMap((n) => [...(n.path ? [n.path] : []), ...paths(n.children)])

/**
 * 关联对象链接：批次跳转到批次作业页，其它实体跳转到目标列表并按 id 过滤（?id=）。
 * 无目标页面（子表 / 内部实体）时只显示文本。
 *
 * @param target - 目标实体编码
 * @param id - 目标记录 id
 * @param label - 显示文本
 * @param mono - 是否等宽字体
 */
export function RefLink({
  target,
  id,
  label,
  mono = false,
}: {
  target: string
  id: string
  label: string
  /** 等宽字体（批次号等编码） */
  mono?: boolean
}) {
  const { data } = useMesMeta()
  const menus = useMyMenus('workspace')
  const e = data?.entities.find((x) => x.code === target)
  // 仅链接到当前用户可访问的页面
  const visible = new Set(paths(menus.data?.menus ?? []))
  const want = target === 'lot' ? '/mes/lot-console' : e && `/mes/${e.url}`
  const base = target === 'lot' ? { lot: id } : { id }
  // 已并入合并菜单的页面：跳转到合并页对应页签
  const moved =
    want && !visible.has(want)
      ? resolveRedirect(menus.data?.redirects, want, base)
      : null
  const path = want && visible.has(want) ? want.slice(1) : moved?.path.slice(1)
  if (!path) return <>{label}</>
  return (
    <Link
      to='/$'
      params={{ _splat: path }}
      search={(moved?.search ?? base) as never}
      className={cn(
        'text-blue-600 underline-offset-2 hover:underline dark:text-blue-400',
        mono && 'font-mono'
      )}
      onClick={(ev) => ev.stopPropagation()}
    >
      {label}
    </Link>
  )
}
