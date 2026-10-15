import { t } from '@/i18n'
import { Pencil, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'

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
        <Button
          size='icon'
          variant='ghost'
          aria-label={t('common.edit')}
          onClick={onEdit}
        >
          <Pencil className='size-4' />
        </Button>
      )}
      {onDelete && (
        <Button
          size='icon'
          variant='ghost'
          aria-label={t('common.delete')}
          onClick={onDelete}
        >
          <Trash2 className='size-4 text-destructive' />
        </Button>
      )}
    </div>
  )
}
