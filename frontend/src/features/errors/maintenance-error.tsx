import { ErrorPage } from './error-page'

export function MaintenanceError() {
  return <ErrorPage code={503} />
}
