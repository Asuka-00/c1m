/** 产品模块：向通用实体页面注册的 UI 扩展（单位换算、产品详情的 BOM 页签）。 */
import { t } from '@/i18n'
import type { MesExtensions } from '@/features/mes/common/types'
import { BomTab } from './bom-tab'
import { UomConverter } from './uom-converter'

/** 产品模块的 UI 扩展。 */
export const extensions: MesExtensions = {
  rowPanels: { uom: UomConverter },
  // F3：BOM 只挂在产品详情，物料详情没有
  detailTabs: {
    product: [
      { key: 'bom', label: () => t('mes.bomTab.title'), Component: BomTab },
    ],
  },
}
