/** 测试用：各语言合并后的完整语言包（宽松类型，便于按路径取值）。 */
import { resources } from '@/i18n/resources'

/* eslint-disable @typescript-eslint/no-explicit-any */
type Loose = Record<string, any>

export const zh: Loose = resources['zh-CN']
export const ja: Loose = resources.ja
export const en: Loose = resources.en
