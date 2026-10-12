import { createFileRoute } from '@tanstack/react-router'
import { MaintenanceError } from '@/features/shell/errors/maintenance-error'

export const Route = createFileRoute('/(errors)/503')({
  component: MaintenanceError,
})
