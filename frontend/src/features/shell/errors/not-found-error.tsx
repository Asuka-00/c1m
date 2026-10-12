import { ErrorPage } from './error-page'

export function NotFoundError() {
  return <ErrorPage code={404} />
}
