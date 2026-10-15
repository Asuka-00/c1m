/** P3 即将到期人员汇总（D62-8 / D64）：保持后端顺序，兜底过滤已过期，0 天（当天）仍有效。 */
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { useTenantKey } from '@/lib/api/hooks'
import {
  qualExpiringApi,
  visibleExpiring,
  type QualExpiringReport,
  type QualExpiringRow,
} from '@/lib/api/mes/qual-expiring'
import { Badge } from '@/components/ui/badge'
import { Page } from '@/components/crud'
import { DataCard } from './report-parts'

/** 汇总视图（无数据请求，便于测试）。 */
export function QualExpiringView({ data }: { data?: QualExpiringReport }) {
  const rows = visibleExpiring(data?.rows ?? [])
  return (
    <>
      <div className='flex flex-wrap items-center gap-3 text-sm text-muted-foreground'>
        {data && (
          <span data-testid='qual-exp-warn'>
            {t('mes.qual.warnDays', { n: data.warn_days })}
          </span>
        )}
        {data?.timezone && (
          <span>{t('mes.ctMove.timezone', { tz: data.timezone })}</span>
        )}
        {data?.mock && (
          <Badge variant='outline' data-testid='qual-exp-mock'>
            {t('mes.ctMove.mock')}
          </Badge>
        )}
      </div>
      <DataCard<QualExpiringRow>
        title={t('mes.qual.expiringTitle')}
        rows={rows}
        max={200}
        exportName='qual-expiring'
        cols={[
          { head: t('mes.qual.user'), get: (r) => r.username },
          { head: t('mes.ctMove.operation'), get: (r) => r.operation },
          {
            head: t('mes.qual.equipmentType'),
            get: (r) => r.equipment_type ?? t('mes.qual.anyEquipment'),
          },
          { head: t('mes.qual.expiresOn'), get: (r) => r.expires_on },
          {
            head: t('mes.qual.daysLeft'),
            get: (r) =>
              r.days_left === 0 ? t('mes.qual.lastDay') : r.days_left,
            text: (r) => r.days_left,
            right: true,
          },
        ]}
      />
    </>
  )
}

export default function QualExpiring() {
  const tk = useTenantKey()
  const q = useQuery({
    queryKey: ['mes', 'exec', tk, 'qual-expiring'],
    queryFn: () => qualExpiringApi.list(),
  })
  return (
    <Page title={t('menu.mes-qual-expiring')} description={t('mes.qual.hint')}>
      <QualExpiringView data={q.data} />
    </Page>
  )
}
