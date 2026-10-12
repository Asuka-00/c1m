import { useState } from 'react'

/** CRUD 页面的对话框状态：当前正在编辑 / 删除的行。 */
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
