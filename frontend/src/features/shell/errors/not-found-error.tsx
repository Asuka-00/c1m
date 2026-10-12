/** 404 页面。 */
import { ErrorPage } from './error-page'

/** 404 页面不存在。 */
export function NotFoundError() {
  return <ErrorPage code={404} />
}
