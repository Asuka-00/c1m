/** 把 "CODE · Name" 形式的标签拆分为编码与名称。 */
export function splitLabel(s: unknown): [string, string] {
  const v = s == null ? '' : String(s)
  const i = v.indexOf(' · ')
  return i < 0 ? [v, ''] : [v.slice(0, i), v.slice(i + 3)]
}
