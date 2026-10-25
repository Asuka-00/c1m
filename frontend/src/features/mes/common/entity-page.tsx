/** MES 实体通用页面（菜单组件 `mes:<code>`）。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Loader2 } from 'lucide-react'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi, type MesRow } from '@/lib/api/mes/common'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Page, useListParams } from '@/components/crud'
import {
  EXTRA_ACTIONS,
  EXTRA_COLUMNS,
  ROW_PANELS,
} from '@/features/mes/registry'
import { NotFoundError } from '@/features/shell/errors/not-found-error'
import { ChildTable } from './child-table'
import { EntityTable } from './entity-table'
import { entityLabel, rowLabel } from './labels'
import { useMesFilters } from './use-mes-filters'
import { useMesEntity, useMesMeta } from './use-mes-meta'

/** 单个 MES 实体的后端驱动页面（菜单组件 `mes:<code>`）。
 *  从通知等链接带 `?id=` 进入时直接打开该记录的详情。 */
export function MesEntityPage({ code }: { code: string }) {
  const { entity, isLoading } = useMesEntity(code)
  const filters = useMesFilters(entity)
  const params = useListParams(filters)
  const tk = useTenantKey()
  const [detail, setDetail] = useState<MesRow | null>(null)
  const [closed, setClosed] = useState<string>()
  const hasDetail =
    !!entity && (entity.children.length > 0 || !!ROW_PANELS[code])
  const focus = hasDetail ? params.filters.id : undefined
  const linked = useQuery({
    queryKey: ['mes', code, 'row', tk, focus],
    queryFn: () => mesApi.get(code, focus!),
    enabled: !!focus && closed !== focus,
  })
  const shown =
    detail ?? (focus && closed !== focus ? (linked.data ?? null) : null)
  if (isLoading) return <Loader2 className='mx-auto mt-24 animate-spin' />
  if (!entity) return <NotFoundError />
  return (
    <Page title={entityLabel(code)}>
      <EntityTable
        entity={entity}
        params={params}
        extraActions={EXTRA_ACTIONS[code]}
        extraColumns={EXTRA_COLUMNS[code]}
        onOpenChildren={hasDetail ? setDetail : undefined}
      />
      <Dialog
        open={!!shown}
        onOpenChange={(o) => {
          if (o) return
          setDetail(null)
          setClosed(focus)
        }}
      >
        <DialogContent className='max-h-[95vh] overflow-y-auto sm:max-w-6xl'>
          {shown && <Detail code={code} row={shown} />}
        </DialogContent>
      </Dialog>
    </Page>
  )
}

function Detail({ code, row }: { code: string; row: MesRow }) {
  const { entity } = useMesEntity(code)
  const { data: meta } = useMesMeta()
  const Panel = ROW_PANELS[code]
  if (!entity || !meta) return null
  const kids = entity.children
    .map((c) => meta.entities.find((x) => x.code === c))
    .filter((x) => !!x)
  const tabs = [
    ...(Panel ? [{ key: '_panel', label: t(`mes.panel.${code}`) }] : []),
    ...kids.map((k) => ({ key: k.code, label: entityLabel(k.code) })),
  ]
  return (
    <>
      <DialogHeader>
        <DialogTitle>
          {entityLabel(code)}: {rowLabel(row, entity.label_field)}
        </DialogTitle>
        <DialogDescription>{t('mes.detailDesc')}</DialogDescription>
      </DialogHeader>
      <Tabs defaultValue={tabs[0]?.key}>
        {tabs.length > 1 && (
          <TabsList>
            {tabs.map((x) => (
              <TabsTrigger key={x.key} value={x.key}>
                {x.label}
              </TabsTrigger>
            ))}
          </TabsList>
        )}
        {Panel && (
          <TabsContent value='_panel'>
            <Panel row={row} />
          </TabsContent>
        )}
        {kids.map((k) => (
          <TabsContent key={k.code} value={k.code}>
            <ChildTable
              code={k.code}
              parentCode={code}
              parentId={row.id}
              parentRow={row}
            />
          </TabsContent>
        ))}
      </Tabs>
    </>
  )
}
