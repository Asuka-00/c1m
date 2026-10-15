import { createContext } from 'react'

/**
 * 嵌入模式：页面作为合并菜单的页签内容渲染时为 true，
 * 此时不再渲染页头与外层容器（标题由合并页显示），只保留说明、操作按钮与内容。
 */
export const PageEmbedContext = createContext(false)
