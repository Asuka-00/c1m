import { createFileRoute } from '@tanstack/react-router'
import { DynamicPage } from '@/features/shell/dynamic/dynamic-page'

// "/" is resolved through the backend menu like every other page
export const Route = createFileRoute('/_authenticated/')({
  component: () => <DynamicPage path='/' />,
})
