/** 批次操作台页面：批次头部信息、阶段步骤条、作业面板、检查 / Hold / 拆合批卡片。 */
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useSearch } from '@tanstack/react-router'
import { t } from '@/i18n'
import { History, Loader2, RefreshCw } from 'lucide-react'
import { useTenantKey } from '@/lib/api/hooks'
import { execApi } from '@/lib/api/mes/execution'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Page } from '@/components/crud'
import { IconButton } from '@/components/icon-button'
import { RefSelect } from '@/features/mes/common/ref-select'
import { DispatchQueue, LotScan } from '../dispatch-queue'
import { Console } from './console'

/** 批次操作台：选择批次，填写输入并执行下一阶段。 */
export default function LotConsolePage() {
  const search = useSearch({ strict: false }) as Record<string, unknown>
  const nav = useNavigate()
  const lotId = (search.lot as string) || ''
  const tk = useTenantKey()
  const ctx = useQuery({
    queryKey: ['mes', 'exec', tk, lotId],
    queryFn: () => execApi.context(lotId),
    enabled: !!lotId,
  })
  const setLot = (id: string | null) =>
    nav({
      to: '/$',
      params: { _splat: 'mes/lot-console' },
      search: (id ? { lot: id } : {}) as never,
    })
  return (
    <Page
      title={t('menu.mes-lot-console')}
      description={t('mes.exec.consoleHint')}
      actions={
        lotId && (
          <Button variant='outline' asChild>
            <Link
              to='/$'
              params={{ _splat: 'mes/lot-history' }}
              search={{ tab: 'mes-lot-trace', lot: lotId } as never}
            >
              <History className='size-4' />
              {t('menu.mes-lot-trace')}
            </Link>
          </Button>
        )
      }
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
        <Console key={`${lotId}-${ctx.dataUpdatedAt}`} cx={ctx.data} />
      )}
    </Page>
  )
}
