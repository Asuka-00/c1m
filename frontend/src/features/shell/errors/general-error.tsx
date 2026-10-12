import { ErrorPage } from './error-page'

export function GeneralError({
  minimal = false,
}: {
  minimal?: boolean
  className?: string
}) {
  return <ErrorPage code={500} minimal={minimal} />
}
