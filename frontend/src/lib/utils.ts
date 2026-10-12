import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** 合并 className（clsx + tailwind-merge 去重冲突的类）。 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** 延时指定毫秒（默认 1000）。 */
export function sleep(ms: number = 1000) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * 生成带省略号的分页页码
 * @param currentPage - 当前页码（从 1 开始）
 * @param totalPages - 总页数
 * @returns 页码与省略号字符串组成的数组
 *
 * 示例：
 * - 页数较少（≤5 页）: [1, 2, 3, 4, 5]
 * - 靠近开头: [1, 2, 3, 4, '...', 10]
 * - 位于中间: [1, '...', 4, 5, 6, '...', 10]
 * - 靠近末尾: [1, '...', 7, 8, 9, 10]
 */
export function getPageNumbers(currentPage: number, totalPages: number) {
  const maxVisiblePages = 5 // 最多显示的页码按钮数
  const rangeWithDots = []

  if (totalPages <= maxVisiblePages) {
    // 总页数不超过 5 时显示全部页码
    for (let i = 1; i <= totalPages; i++) {
      rangeWithDots.push(i)
    }
  } else {
    // 始终显示第一页
    rangeWithDots.push(1)

    if (currentPage <= 3) {
      // 靠近开头：[1] [2] [3] [4] ... [10]
      for (let i = 2; i <= 4; i++) {
        rangeWithDots.push(i)
      }
      rangeWithDots.push('...', totalPages)
    } else if (currentPage >= totalPages - 2) {
      // 靠近末尾：[1] ... [7] [8] [9] [10]
      rangeWithDots.push('...')
      for (let i = totalPages - 3; i <= totalPages; i++) {
        rangeWithDots.push(i)
      }
    } else {
      // 位于中间：[1] ... [4] [5] [6] ... [10]
      rangeWithDots.push('...')
      for (let i = currentPage - 1; i <= currentPage + 1; i++) {
        rangeWithDots.push(i)
      }
      rangeWithDots.push('...', totalPages)
    }
  }

  return rangeWithDots
}

/**
 * 显示名称的首字母缩写：首个单词的首字符 + 最后一个单词的首字符；
 * 只有一个单词时取前两个字符；为空时为 `?`。
 */
export function getDisplayNameInitials(displayName: string): string {
  const parts = displayName.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase()
  }
  const first = parts[0][0] ?? ''
  const last = parts[parts.length - 1]?.[0] ?? ''
  return (first + last).toUpperCase()
}
