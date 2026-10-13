/** 启用 / 禁用状态的选项与筛选定义（用户、角色、权限通用）。 */
import { t } from '@/i18n'
import type { FilterDef } from '@/components/crud'

/** 状态单选 / 下拉选项（active / disabled）。 */
export const statusOptions = () => [
  { value: 'active', label: t('rbac.enabled') },
  { value: 'disabled', label: t('rbac.disabled') },
]

/** 状态下拉筛选。 */
export const statusFilter = (name = 'status'): FilterDef => ({
  type: 'select',
  name,
  label: t('table.allStatuses'),
  options: statusOptions(),
})
