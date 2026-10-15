/** 平台控制台 · 通知渠道：查看已登记渠道并启用 / 停用（全平台生效）。 */
import { useQuery } from '@tanstack/react-query'
import { currentLanguage, t } from '@/i18n'
import { api } from '@/lib/api'
import { useApiMutation } from '@/lib/api/hooks'
import { Switch } from '@/components/ui/switch'
import { DataTable, Page } from '@/components/crud'
import { clientList } from '@/components/crud/client-list'
import { useLocalListParams } from '@/components/crud/use-local-list-params'

/** 渠道标签（"en|zh|ja"）按当前语言取值。 */
const label = (s: string) => {
  const parts = s.split('|')
  const lang = currentLanguage()
  const idx = lang === 'zh-CN' ? 1 : lang === 'ja' ? 2 : 0
  return parts[idx] ?? parts[0]
}

export default function NotifyChannelsPage() {
  const q = useQuery({
    queryKey: ['platform', 'channels'],
    queryFn: api.platform.channels,
  })
  const lp = useLocalListParams()
  const set = useApiMutation(
    (b: { code: string; enabled: boolean }) =>
      api.platform.setChannel(b.code, b.enabled),
    [['platform', 'channels']],
    t('platform.channelSaved')
  )
  const page = clientList(q.data?.data ?? [], lp, {
    text: (r) => `${r.code} ${r.label}`,
  })
  return (
    <Page title={t('menu.p-channels')} description={t('platform.channelsDesc')}>
      <DataTable
        rows={page.rows}
        total={page.total}
        params={lp}
        filters={[{ type: 'text', name: 'q' }]}
        loading={q.isLoading}
        rowKey={(r) => r.code}
        columns={[
          {
            header: t('platform.channel'),
            cell: (r) => <span className='font-medium'>{label(r.label)}</span>,
          },
          {
            header: t('platform.code'),
            cell: (r) => <span className='font-mono text-xs'>{r.code}</span>,
          },
          {
            header: t('platform.enabled'),
            cell: (r) => (
              <Switch
                checked={r.enabled}
                aria-label={r.code}
                onCheckedChange={(v) =>
                  set.mutate({ code: r.code, enabled: v })
                }
              />
            ),
          },
        ]}
      />
    </Page>
  )
}
