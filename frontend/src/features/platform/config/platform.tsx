/** 平台控制台 · 系统配置（平台默认值，所有租户继承）。 */
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { api } from '@/lib/api'
import { Page } from '@/components/crud'
import { ConfigGroups } from './index'

export default function PlatformConfigPage() {
  const q = useQuery({
    queryKey: ['config', 'platform'],
    queryFn: api.config.platform,
  })
  return (
    <Page title={t('menu.p-config')} description={t('config.platformDesc')}>
      <ConfigGroups
        loading={q.isLoading}
        groups={q.data?.data}
        scope='platform'
        canEdit
      />
    </Page>
  )
}
