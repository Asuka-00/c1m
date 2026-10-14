/** MES 页面汇总。 */
import { pages as equipment } from './equipment/pages'
import { pages as execution } from './execution/pages'
import { pages as map } from './map/pages'
import { pages as planning } from './planning/pages'
import { pages as reticle } from './reticle/pages'

/** 全部 MES 页面（由各业务域模块的页面组合而成）。 */
export const pages = {
  ...equipment,
  ...planning,
  ...execution,
  ...map,
  ...reticle,
}
