/** 带禁用原因的按钮：禁用时外层可聚焦，悬停 / 键盘聚焦都会显示原因（FE-02，同 F3 BOM 页签）。 */
import { Button } from '@/components/ui/button'
import { IconTooltip } from '@/components/icon-button'

/**
 * @param label - 按钮文字
 * @param reason - 禁用原因；为空时按钮可用
 * @param onClick - 点击回调
 * @param testId - 按钮的 data-testid
 */
export function ReasonButton({
  label,
  reason,
  onClick,
  testId,
  variant = 'outline',
  size = 'sm',
}: {
  label: string
  reason?: string | null
  onClick: () => void
  testId?: string
  variant?: 'outline' | 'default' | 'ghost'
  size?: 'sm' | 'default'
}) {
  if (!reason)
    return (
      <Button
        size={size}
        variant={variant}
        onClick={onClick}
        data-testid={testId}
      >
        {label}
      </Button>
    )
  return (
    <IconTooltip label={reason}>
      <span
        tabIndex={0}
        className='inline-flex'
        aria-label={`${label}: ${reason}`}
        data-testid={testId ? `${testId}-reason` : 'disabled-reason'}
      >
        <Button
          size={size}
          variant={variant}
          disabled
          tabIndex={-1}
          data-testid={testId}
        >
          {label}
        </Button>
      </span>
    </IconTooltip>
  )
}
