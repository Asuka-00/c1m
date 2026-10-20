import { en, ja, zh } from '@/test-utils/locales'
import { describe, expect, it } from 'vitest'
import { descriptionIssues, descriptionProblem } from './description-style'

describe('说明文案', () => {
  it.each([
    ['zh-CN', zh],
    ['en', en],
    ['ja', ja],
  ])('%s 的说明简短且不含实现细节', (_, b) => {
    expect(descriptionIssues(b)).toEqual([])
  })
  it('识别环境变量、API 与过长文案', () => {
    expect(descriptionProblem('后台扫描（QTIME_SWEEP_SECONDS）')).toBe(
      'env-var-like token'
    )
    expect(descriptionProblem('Calls the API')).toBe('mentions API')
    expect(descriptionProblem('字'.repeat(41))).toBe('too long')
    expect(descriptionProblem('x'.repeat(101))).toBe('too long')
    expect(descriptionProblem('查看等待中批次的 Q-Time 剩余时间')).toBeNull()
    expect(
      descriptionIssues({ a: { desc: 'Uses API' }, b: { title: 'API' } })
    ).toEqual(['a.desc: mentions API'])
  })
})
