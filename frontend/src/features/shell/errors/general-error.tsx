/** 500 页面。 */
import { ErrorPage } from './error-page'

/** 500 通用错误页面（可用于路由错误边界）。 */
export function GeneralError({
  minimal = false,
}: {
  minimal?: boolean
  className?: string
}) {
  return <ErrorPage code={500} minimal={minimal} />
}
