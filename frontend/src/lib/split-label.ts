/** Splits "CODE · Name" labels into code and name. */
export function splitLabel(s: unknown): [string, string] {
  const v = s == null ? '' : String(s)
  const i = v.indexOf(' · ')
  return i < 0 ? [v, ''] : [v.slice(0, i), v.slice(i + 3)]
}
