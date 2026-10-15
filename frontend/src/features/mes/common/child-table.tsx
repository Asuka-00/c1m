/** MES 子表组件（行详情抽屉中的子表标签页）。 */
import { useLocalListParams } from '@/components/crud'
import { EntityTable } from './entity-table'
import { useMesEntity } from './use-mes-meta'

/** 某父级的子表行（固定父级筛选，本地分页状态）。 */
export function ChildTable({
  code,
  parentCode,
  parentId,
}: {
  code: string
  parentCode: string
  parentId: string
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
    />
  )
}
