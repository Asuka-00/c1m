import { createFileRoute } from '@tanstack/react-router'
import { SplatPage } from '@/features/dynamic/splat-page'

// Catch-all: every app page is resolved from GET /menus/me at runtime.
export const Route = createFileRoute('/_authenticated/$')({
  component: SplatPage,
})
