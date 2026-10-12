/** 503 页面。 */
import { ErrorPage } from './error-page'

/** 503 维护中页面。 */
export function MaintenanceError() {
  return <ErrorPage code={503} />
}
