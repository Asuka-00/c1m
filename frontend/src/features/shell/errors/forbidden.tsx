/** 403 页面。 */
import { ErrorPage } from './error-page'

/** 403 无权限页面。 */
export function ForbiddenError() {
  return <ErrorPage code={403} />
}
