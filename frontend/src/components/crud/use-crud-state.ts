import { useState } from 'react'

/** Dialog state for a CRUD page: which row is being edited/deleted. */
export function useCrudState<T>() {
  const [editing, setEditing] = useState<T | null>(null)
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState<T | null>(null)
  return {
    editing,
    creating,
    deleting,
    openCreate: () => setCreating(true),
    openEdit: (r: T) => setEditing(r),
    openDelete: (r: T) => setDeleting(r),
    formOpen: creating || editing !== null,
    closeForm: () => {
      setCreating(false)
      setEditing(null)
    },
    closeDelete: () => setDeleting(null),
  }
}
