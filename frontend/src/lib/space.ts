/** 菜单空间：租户工作区与平台管理控制台。 */

/**
 * 是否为平台管理控制台路径（`/platform` 及其子路径）。
 *
 * @param path 路由路径（不含查询串）。
 */
export const isPlatformPath = (path: string) =>
  path === '/platform' || path.startsWith('/platform/')
