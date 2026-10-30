/** 批次操作台页面：作业（概要 / 作业面板 / 检查 / Hold / 拆合批）、履历、晶圆、配方执行四个页签。 */
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { t } from '@/i18n'
import { Loader2, RefreshCw } from 'lucide-react'
import { useTenantKey } from '@/lib/api/hooks'
import { execApi } from '@/lib/api/mes/execution'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Page } from '@/components/crud'
import { IconButton } from '@/components/icon-button'
import { RefSelect } from '@/features/mes/common/ref-select'
import { DispatchQueue, LotScan } from '../dispatch/dispatch-queue'
import { LOT_VIEWS, type LotView, lotPageLink } from '../shared/lot-links'
import {
  LotHistoryCard,
  RecipeRunCard,
  WaferStatusCard,
} from '../trace/lot-trace'
import { Console } from './console'

/** 批次操作台：选择批次，填写输入并执行下一阶段。 */
export default function LotConsolePage() {
  const search = useSearch({ strict: false }) as Record<string, unknown>
  const nav = useNavigate()
  const lotId = (search.lot as string) || ''
  const view = LOT_VIEWS.includes(search.view as LotView)
    ? (search.view as LotView)
    : 'ops'
  const tk = useTenantKey()
  const ctx = useQuery({
    queryKey: ['mes', 'exec', tk, lotId],
    queryFn: () => execApi.context(lotId),
    enabled: !!lotId,
  })
  const go = (id: string | null, v: LotView = 'ops') =>
    nav(
      id
        ? lotPageLink(id, v)
        : { to: '/$', params: { _splat: 'mes/lot-console' } }
    )
  const setLot = (id: string | null) => go(id)
  return (
    <Page
      title={t('menu.mes-lot-console')}
      description={t('mes.exec.consoleHint')}
    >
      <div className='flex flex-wrap items-center gap-2'>
        <LotScan onLot={setLot} />
        <Label className='shrink-0'>{t('mes.entity.lot')}</Label>
        <div className='w-72'>
          <RefSelect
            id='console-lot'
            target='lot'
            value={lotId || null}
            label={ctx.data ? String(ctx.data.lot.code) : null}
            onChange={(id) => setLot(id)}
          />
        </div>
        {lotId && (
          <IconButton
            label={t('mes.exec.refresh')}
            variant='ghost'
            onClick={() => ctx.refetch()}
          >
            <RefreshCw className='size-4' />
          </IconButton>
        )}
      </div>
      {!lotId && <DispatchQueue onLot={setLot} />}
      {ctx.isLoading && <Loader2 className='animate-spin' />}
      {ctx.data && (
        <Tabs value={view} onValueChange={(v) => go(lotId, v as LotView)}>
          <TabsList>
            {LOT_VIEWS.map((v) => (
              <TabsTrigger key={v} value={v} data-testid={`lot-view-${v}`}>
                {t(`mes.lotView.${v}`)}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value='ops'>
            <Console key={`${lotId}-${ctx.dataUpdatedAt}`} cx={ctx.data} />
          </TabsContent>
          <TabsContent value='history'>
            <LotHistoryCard lotId={lotId} />
          </TabsContent>
          <TabsContent value='wafers'>
            <WaferStatusCard lotId={lotId} />
          </TabsContent>
          <TabsContent value='runs'>
            <RecipeRunCard lotId={lotId} />
          </TabsContent>
        </Tabs>
      )}
    </Page>
  )
}
