/** 只有图标的按钮：悬停 / 键盘聚焦时显示多语言提示，同一文本用作 aria-label。 */
import * as React from 'react'
import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'

type Side = React.ComponentProps<typeof TooltipContent>['side']

/**
 * 给任意可聚焦元素加悬停 / 聚焦提示（不改其样式）。
 * 子元素必须能接收 ref 与事件（如原生 button 或 Button）。
 */
export function IconTooltip({
  label,
  side,
  children,
}: {
  label: string
  side?: Side
  children: React.ReactElement
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side={side}>{label}</TooltipContent>
    </Tooltip>
  )
}

export type IconButtonProps = Omit<
  React.ComponentProps<typeof Button>,
  'aria-label' | 'title'
> & {
  /** 按钮作用（已本地化）：用于悬停提示与 aria-label */
  label: string
  /** 提示显示位置 */
  tooltipSide?: Side
}

/**
 * 图标按钮（shadcn Button size=icon + Tooltip）。
 * 禁用时外包一个可聚焦的 span，使提示仍可在悬停 / 聚焦时显示。
 * 可放在 DropdownMenuTrigger / PopoverTrigger 的 asChild 中（ref 与事件透传到 Button）。
 */
export function IconButton({
  label,
  tooltipSide,
  size = 'icon',
  disabled,
  ...props
}: IconButtonProps) {
  const btn = (
    <Button size={size} aria-label={label} disabled={disabled} {...props} />
  )
  return (
    <IconTooltip label={label} side={tooltipSide}>
      {disabled ? (
        <span
          tabIndex={0}
          className='inline-flex'
          data-testid='icon-button-disabled-wrap'
        >
          {btn}
        </span>
      ) : (
        btn
      )}
    </IconTooltip>
  )
}
