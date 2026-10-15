/** 引用字段的关联对象链接。 */
import { Link } from '@tanstack/react-router'
import { useMyMenus } from '@/lib/api/hooks'
import { cn } from '@/lib/utils'
import { findPage } from '@/features/shell/dynamic/merged'
import { useMesMeta } from './use-mes-meta'

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
  // 仅链接到当前用户可访问的页面（合并菜单的页签跳转到合并页 ?tab=）
  const key = target === 'lot' ? 'mes-lot-console' : e && `mes-${e.code}`
  const page = key ? findPage(menus.data?.menus ?? [], key) : null
  const base = target === 'lot' ? { lot: id } : { id }
  const path = page?.path.slice(1)
  if (!path) return <>{label}</>
  return (
    <Link
      to='/$'
      params={{ _splat: path }}
      search={(page?.tab ? { ...base, tab: page.tab } : base) as never}
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
