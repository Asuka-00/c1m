/**
 * Vitest 全局初始化：组件测试以英文文案断言，而应用默认语言为 zh-CN，
 * 因此在每个测试前固定切换到 en，保证结果与浏览器 / localStorage 状态无关。
 */
import '@/i18n'
import i18n from 'i18next'
import { beforeEach } from 'vitest'

beforeEach(async () => {
  if (i18n.language !== 'en') await i18n.changeLanguage('en')
})
