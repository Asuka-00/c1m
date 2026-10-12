/** 401 页面。 */
import { ErrorPage } from './error-page'

/** 401 未登录页面。 */
export function UnauthorisedError() {
  return <ErrorPage code={401} />
}
