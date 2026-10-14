/**
 * MES 按钮权限：统一读取 `GET /mes/_meta` 返回的 `perms`（后端按当前用户
 * 过滤过的权限码，超级用户由后端 `ctx.can` 放行），供按钮显示 / 禁用判断。
 * 前端判断只影响界面，后端接口仍做最终校验。
 */
import { useCallback, useMemo } from 'react'
import { useMesMeta } from './use-mes-meta'

/** 与后端 `permissions.py` 一致的 MES 操作权限码。 */
export const MES_PERM = {
  /** 阶段作业：Move In / Track In / Track Out / Move Out、批量作业、载具操作、交接班 */
  execWrite: 'mes.exec:write',
  /** 卡控强制放行 */
  execOverride: 'mes.exec:override',
  /** Hold / Release */
  execHold: 'mes.exec:hold',
  /** 拆批 */
  execSplit: 'mes.exec:split',
  /** 合批 */
  execMerge: 'mes.exec:merge',
  /** 跳站 */
  execJump: 'mes.exec:jump',
  /** 在制报废 / 补数 / 优先级 */
  execAdjust: 'mes.exec:adjust',
  /** 工单状态迁移 */
  woRelease: 'mes.wo:release',
  /** 开批 / 撤销开批 */
  lotStart: 'mes.lot:start',
  /** 手动改设备 E10 状态 */
  equipmentE10: 'mes.equipment:e10',
  /** 设备 PM */
  equipmentPm: 'mes.equipment:pm',
  /** 机台上料 / 卸料（P1 / B3） */
  equipmentMount: 'mes.equipment:mount',
  /** 坐标图导入（P1 / B4） */
  mapImport: 'mes.map:import',
  /** 坐标图查询（P1 / B4） */
  mapRead: 'mes.map:read',
  /** BOM 新建 / 编辑草稿 / 复制（P1 / F3） */
  bomWrite: 'mes.bom:write',
  /** BOM 生效 / 作废（P1 / F3） */
  bomActivate: 'mes.bom:activate',
} as const

export type MesPerm = (typeof MES_PERM)[keyof typeof MES_PERM] | (string & {})

/**
 * 当前用户的 MES 权限判断。
 *
 * @returns `can(code)`：是否拥有权限码；元数据未加载时一律为 false（按钮默认不可用）
 */
export function useMesCan() {
  const { data } = useMesMeta()
  const perms = data?.perms
  const set = useMemo(() => new Set(perms ?? []), [perms])
  return useCallback((code: MesPerm) => set.has(code), [set])
}
