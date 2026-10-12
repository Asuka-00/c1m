import { useState } from 'react'

/**
 * 确认对话框的状态 Hook
 * @param initialState string | null
 * @returns 状态值及其更新函数（再次设置相同值会关闭）。
 * @example const [open, setOpen] = useDialogState<"approve" | "reject">()
 */
export default function useDialogState<T extends string | boolean>(
  initialState: T | null = null
) {
  const [open, _setOpen] = useState<T | null>(initialState)

  const setOpen = (str: T | null) =>
    _setOpen((prev) => (prev === str ? null : str))

  return [open, setOpen] as const
}
