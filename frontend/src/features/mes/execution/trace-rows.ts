/**
 * 参与谱系的行（a46d232）：已撤销转换节点（`undone=true`）只展示，不计入数量、不做批次跳转。
 */
export const genealogyRows = <T extends { undone?: unknown }>(rows: T[]) =>
  rows.filter((r) => r.undone !== true)
