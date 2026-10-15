/** 批次操作台共用类型。 */

/** 数据采集录入：`${item}|${unit}|${site}` -> 录入值 */
export type Dc = Record<string, string>
/** 报废录入行（按数量或按晶圆）。 */
export type Scrap = { unit_id?: string; qty?: string; reason_id: string }
