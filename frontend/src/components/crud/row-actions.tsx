import { t } from '@/i18n'
import { Pencil, Trash2 } from 'lucide-react'
import { IconButton } from '@/components/icon-button'

/** 表格行的编辑 / 删除操作按钮（按权限与回调显示）。 */
export function RowActions({
  onEdit,
  onDelete,
  children,
}: {
  onEdit?: () => void
  onDelete?: () => void
  children?: React.ReactNode
}) {
  return (
    <div className='flex justify-end gap-1'>
      {children}
      {onEdit && (
        <IconButton label={t('common.edit')} variant='ghost' onClick={onEdit}>
          <Pencil className='size-4' />
        </IconButton>
      )}
      {onDelete && (
        <IconButton
          label={t('common.delete')}
          variant='ghost'
          onClick={onDelete}
        >
          <Trash2 className='size-4 text-destructive' />
        </IconButton>
      )}
    </div>
  )
}
