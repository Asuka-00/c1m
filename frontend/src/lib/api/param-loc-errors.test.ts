import { AxiosError, AxiosHeaders } from 'axios'
import i18n, { t } from '@/i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import { mapApiError } from '@/lib/api/mes/map'
import { transformErrorText } from '@/features/mes/execution/transform-plan'
import { mapErrorMessage } from '@/features/mes/map/map-errors'
import {
  startFieldErrors,
  startTopErrors,
} from '@/features/mes/planning/start-errors'
import { bomError } from '@/features/mes/product/bom-errors'
import { paramMessage } from './client'

const ax = (detail: unknown) => {
  const e = new AxiosError('422')
  e.response = {
    status: 422,
    data: { detail },
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
  }
  return e
}
const tz = {
  loc: ['query', 'at'],
  msg: 'at: timezone required',
  type: 'timezone_required',
  code: 'timezone_required',
}
const plain = {
  loc: ['path', 'map_id'],
  msg: 'map_id: invalid uuid',
  type: 'value_error',
  code: 'value_error',
}

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

describe('query / path 类 422 不当导入字段（QA 低优先级）', () => {
  it('mapApiError：字段名为参数名、文案先 code 再 type，不出现 query./path.', () => {
    const err = mapApiError(
      ax([tz, plain, { loc: ['body', 'file'], msg: 'file: required' }])
    )
    expect(err).toEqual({
      kind: 'fields',
      fields: [
        { field: 'at', msg: t('mes.err.code.timezone_required') },
        { field: 'map_id', msg: 'invalid uuid' },
        { field: 'file', msg: 'file: required' },
      ],
    })
    const text = mapErrorMessage(err)
    expect(text).not.toMatch(/query\.|path\./)
    expect(text).toContain(`at: ${t('mes.err.code.timezone_required')}`)
  })

  it('仅 type 也能取文案', () => {
    expect(
      paramMessage({ loc: ['query', 'at'], type: 'timezone_required' })
    ).toBe(t('mes.err.code.timezone_required'))
  })

  it('开批：参数错误进顶部提示，不进批次行', () => {
    const e = ax([{ ...tz }])
    expect(startFieldErrors(e)).toBeNull()
    expect(startTopErrors(e)).toEqual([
      `at: ${t('mes.err.code.timezone_required')}`,
    ])
  })

  it('BOM：全是参数错误时不生成字段错误', () => {
    const r = bomError(ax([plain]))
    expect(r.fields).toEqual([])
    expect(r.message).toBe('map_id: invalid uuid')
  })

  it('转换：参数错误显示「参数名: 文案」', () => {
    expect(transformErrorText(ax([tz]))).toBe(
      `at: ${t('mes.err.code.timezone_required')}`
    )
  })
})
