/** 批次操作台页签：作业 / 履历 / 晶圆 / 配方执行。 */
export const LOT_VIEWS = ['ops', 'history', 'wafers', 'runs'] as const
export type LotView = (typeof LOT_VIEWS)[number]

/** 按批次打开操作台的链接；view 指定页签（缺省为作业）。 */
export function lotPageLink(lot: unknown, view: LotView = 'ops') {
  const id = String(lot)
  return {
    to: '/$' as const,
    params: { _splat: 'mes/lot-console' },
    search: (view === 'ops' ? { lot: id } : { lot: id, view }) as never,
  }
}
