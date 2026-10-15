/** 启用 / 禁用状态徽标。 */
import { t } from '@/i18n'
import { Badge } from '@/components/ui/badge'

/** 状态徽标：启用为绿色，禁用为灰色描边。 */
export function StatusBadge({ active }: { active: boolean }) {
  return active ? (
    <Badge className='bg-emerald-600 text-white hover:bg-emerald-600'>
      {t('rbac.enabled')}
    </Badge>
  ) : (
    <Badge variant='outline'>{t('rbac.disabled')}</Badge>
  )
}
