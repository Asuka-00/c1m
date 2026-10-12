import { extensions as common } from './common/extensions'
import type { MesExtensions } from './common/types'
import { extensions as execution } from './execution/extensions'
import { extensions as lot } from './lot/extensions'
import { extensions as planning } from './planning/extensions'
import { extensions as process } from './process/extensions'
import { extensions as product } from './product/extensions'
import { extensions as warehouse } from './warehouse/extensions'

/**
 * MES UI 模块的组合根（与后端 app/modules.py 对应）：
 * 各业务域向通用实体页面提供实体专用的面板 / 操作。
 * 没有定制 UI 的业务域（factory、equipment、quality）
 * 完全由后端规格渲染。
 */
const MODULES: MesExtensions[] = [
  common,
  product,
  process,
  lot,
  planning,
  warehouse,
  execution,
]

/** 实体专用详情面板（行详情抽屉的第一个标签页）。 */
export const ROW_PANELS = Object.assign(
  {},
  ...MODULES.map((m) => m.rowPanels ?? {})
) as NonNullable<MesExtensions['rowPanels']>

/** 实体专用的额外行操作按钮。 */
export const EXTRA_ACTIONS = Object.assign(
  {},
  ...MODULES.map((m) => m.extraActions ?? {})
) as NonNullable<MesExtensions['extraActions']>
