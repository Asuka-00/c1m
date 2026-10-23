/** MES 子表组件（行详情抽屉中的子表标签页）。 */
import type { MesRow } from '@/lib/api/mes/common'
import { useLocalListParams } from '@/components/crud'
import { EXTRA_ACTIONS } from '@/features/mes/registry'
import { EntityTable } from './entity-table'
import { CHILD_LOCKS } from './row-rules'
import { useMesEntity } from './use-mes-meta'

/** 某父级的子表行（固定父级筛选，本地分页状态）。 */
export function ChildTable({
  code,
  parentCode,
  parentId,
  parentRow,
}: {
  code: string
  parentCode: string
  parentId: string
  /** 父级行（用于判断子表是否锁定） */
  parentRow?: MesRow
}) {
  const { entity } = useMesEntity(code)
  const params = useLocalListParams()
  if (!entity) return null
  const f = entity.fields.find((x) => x.type === 'ref' && x.ref === parentCode)
  if (!f) return null
  return (
    <EntityTable
      entity={entity}
      params={params}
      fixed={{ [f.column]: parentId }}
      extraActions={EXTRA_ACTIONS[code]}
      readOnly={!!parentRow && !!CHILD_LOCKS[parentCode]?.(parentRow)}
    />
  )
}
