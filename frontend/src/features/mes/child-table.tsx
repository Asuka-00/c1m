import { useLocalListParams } from '@/components/crud'
import { EntityTable } from './entity-table'
import { useMesEntity } from './use-mes-meta'

/** Child rows of one parent (fixed parent filter, local paging state). */
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
