/** 设备 OEE 报表：时间稼动率 × 性能稼动率 × 良品率（缺 UPH 不计算性能与 OEE）。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { useTenantKey } from '@/lib/api/hooks'
import { execApi } from '@/lib/api/mes/execution'
import { Badge } from '@/components/ui/badge'
import { Page } from '@/components/crud'
import { DataCard, DateRange } from './report-parts'
import { isoDay, pct } from './report-utils'

/** 设备 OEE 页面。 */
export default function OeeReport() {
  const tk = useTenantKey()
  const [from, setFrom] = useState(isoDay(-6))
  const [to, setTo] = useState(isoDay())
  const q = useQuery({
    queryKey: ['mes', 'exec', tk, 'report-oee', from, to],
    queryFn: () => execApi.oee({ date_from: from, date_to: to }),
    enabled: !!from && !!to && from <= to,
  })
  return (
    <Page
      title={t('menu.mes-oee-report')}
      description={t('mes.report.oeeHint')}
      actions={
        <DateRange from={from} to={to} setFrom={setFrom} setTo={setTo} />
      }
    >
      <DataCard
        title={t('menu.mes-oee-report')}
        rows={q.data ?? []}
        max={500}
        cols={[
          {
            head: t('mes.report.equipment'),
            get: (r) => <span className='font-mono'>{r.equipment}</span>,
          },
          {
            head: t('mes.report.loading'),
            get: (r) => r.loading_h,
            right: true,
          },
          { head: t('mes.report.prd'), get: (r) => r.prd_h, right: true },
          {
            head: t('mes.report.availability'),
            get: (r) => pct(r.availability),
            right: true,
          },
          {
            head: t('mes.report.performance'),
            right: true,
            get: (r) =>
              r.uph_missing ? (
                <Badge variant='outline'>{t('mes.report.uphMissing')}</Badge>
              ) : (
                pct(r.performance)
              ),
          },
          {
            head: t('mes.report.quality'),
            get: (r) => pct(r.quality),
            right: true,
          },
          {
            head: t('mes.report.oee'),
            right: true,
            get: (r) => <span className='font-semibold'>{pct(r.oee)}</span>,
          },
          { head: t('mes.report.good'), get: (r) => r.good, right: true },
          { head: t('mes.report.scrap'), get: (r) => r.scrap, right: true },
        ]}
      />
    </Page>
  )
}
