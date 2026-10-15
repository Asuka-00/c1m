/** MES 业务域模块 UI 扩展的类型定义。 */
import type { ComponentType, ReactNode } from 'react'
import type { MesRow } from '@/lib/api/mes/common'

/** MES 业务域模块向通用实体页面提供的扩展。 */
export interface MesExtensions {
  /** 实体编码 -> 详情面板（行详情抽屉的第一个标签页） */
  rowPanels?: Record<string, ComponentType<{ row: MesRow }>>
  /** 实体编码 -> 额外的行操作按钮 */
  extraActions?: Record<string, (r: MesRow) => ReactNode>
}
