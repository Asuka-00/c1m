import { useState } from 'react'
import { t } from '@/i18n'
import { Loader2 } from 'lucide-react'
import type { MesRow } from '@/lib/api/mes'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Page, useListParams } from '@/components/crud'
import { NotFoundError } from '@/features/errors/not-found-error'
import { ChildTable } from './child-table'
import { EntityTable } from './entity-table'
import { EXTRA_ACTIONS, ROW_PANELS } from './extensions'
import { entityLabel, rowLabel } from './labels'
import { useMesFilters } from './use-mes-filters'
import { useMesEntity, useMesMeta } from './use-mes-meta'

/** Backend-driven page for one MES entity (menu component `mes:<code>`). */
export function MesEntityPage({ code }: { code: string }) {
  const { entity, isLoading } = useMesEntity(code)
  const filters = useMesFilters(entity)
  const params = useListParams(filters)
  const [detail, setDetail] = useState<MesRow | null>(null)
  if (isLoading) return <Loader2 className='mx-auto mt-24 animate-spin' />
  if (!entity) return <NotFoundError />
  const hasDetail = entity.children.length > 0 || !!ROW_PANELS[code]
  return (
    <Page
      title={entityLabel(code)}
      description={t(`mes.module.${entity.module}`)}
    >
      <EntityTable
        entity={entity}
        params={params}
        extraActions={EXTRA_ACTIONS[code]}
        onOpenChildren={hasDetail ? setDetail : undefined}
      />
      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent className='max-h-[95vh] overflow-y-auto sm:max-w-6xl'>
          {detail && <Detail code={code} row={detail} />}
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
            <ChildTable code={k.code} parentCode={code} parentId={row.id} />
          </TabsContent>
        ))}
      </Tabs>
    </>
  )
}
