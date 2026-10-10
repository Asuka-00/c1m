import { ErrorPage } from './error-page'

export function UnauthorisedError() {
  return <ErrorPage code={401} />
}
