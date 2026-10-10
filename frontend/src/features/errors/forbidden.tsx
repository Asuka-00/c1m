import { ErrorPage } from './error-page'

export function ForbiddenError() {
  return <ErrorPage code={403} />
}
