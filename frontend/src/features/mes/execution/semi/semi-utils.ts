/** 单元作业页面的纯函数：Bin 着色、控制图纵轴范围、转换请求组装。 */
import type {
  ConvertBody,
  DieMapDetail,
  SpcChart,
  UnitKind,
} from '@/lib/api/mes/semi'

export type ConvertMode = 'split' | 'assemble' | 'map'

/** Bin 的显示颜色：配置色优先，否则良品绿、坏品红。 */
export function binColor(legend: DieMapDetail['legend'], bin: string): string {
  const b = legend.find((x) => x.bin === bin)
  return b?.color || (b?.is_good ? '#10b981' : '#ef4444')
}

/**
 * 控制图纵轴范围：覆盖全部点与已配置的控制限 / 规格限，上下各留 10%。
 *
 * @returns `[最小值, 最大值]`
 */
export function yRange(c: SpcChart): [number, number] {
  const vals = [
    ...c.points.map((p) => p.mean),
    ...Object.values(c.limits).filter((v): v is number => v != null),
  ]
  if (!vals.length) return [0, 1]
  const lo = Math.min(...vals)
  const hi = Math.max(...vals)
  const pad = (hi - lo || Math.abs(hi) || 1) * 0.1
  return [lo - pad, hi + pad]
}

/** 由界面选项组装转换请求。 */
export function convertBody(
  kind: UnitKind,
  mode: ConvertMode,
  n: number,
  comment: string
): ConvertBody {
  return {
    to_kind: kind,
    per_parent: mode === 'split' ? n : 1,
    per_child: mode === 'assemble' ? n : 1,
    use_map: mode === 'map',
    comment: comment.trim() || undefined,
  }
}
