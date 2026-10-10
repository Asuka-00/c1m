import { useParams } from '@tanstack/react-router'
import { DynamicPage } from './dynamic-page'

/** Catch-all page: resolves the component for the current path from GET /menus/me. */
export function SplatPage() {
  const { _splat } = useParams({ from: '/_authenticated/$' })
  return <DynamicPage path={`/${(_splat ?? '').replace(/\/$/, '')}`} />
}
