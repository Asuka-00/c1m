import { AxiosError, AxiosHeaders } from 'axios'
import i18n, { t } from '@/i18n'
import { afterEach, describe, expect, it } from 'vitest'
import {
  DUPLICATE_KEY_DETAIL,
  isDuplicateKey,
  mesErrorMessage,
} from '@/features/mes/common/required'
import { mockReticleApi, resetReticleMock } from './mes/reticle'

const ax = (status: number, detail: unknown) => {
  const e = new AxiosError(String(status))
  e.response = {
    status,
    data: { detail },
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
  }
  return e
}
afterEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

describe('通用重复键 409（spec.errors.integrity）', () => {
  it('识别：字符串原文；将来对象格式（message 同原文 / code 无 field）', () => {
    expect(isDuplicateKey(ax(409, DUPLICATE_KEY_DETAIL))).toBe(true)
    expect(
      isDuplicateKey(ax(409, { code: 'x', message: DUPLICATE_KEY_DETAIL }))
    ).toBe(true)
    expect(isDuplicateKey(ax(409, { code: 'duplicate_key' }))).toBe(true)
    // BOM 替代料专用对象格式（带 field）不按通用处理
    expect(
      isDuplicateKey(ax(409, { code: 'duplicate', field: 'priority' }))
    ).toBe(false)
    expect(
      isDuplicateKey(ax(409, 'Record is referenced by other records'))
    ).toBe(false)
    expect(isDuplicateKey(ax(422, DUPLICATE_KEY_DETAIL))).toBe(false)
  })
  it.each(['zh-CN', 'en', 'ja'])('%s 显示通用重复文案', async (lng) => {
    await i18n.changeLanguage(lng)
    const m = mesErrorMessage(ax(409, DUPLICATE_KEY_DETAIL), undefined)
    expect(m).toBe(t('mes.err.duplicateKey'))
    expect(m).not.toBe('mes.err.duplicateKey')
    expect(
      mesErrorMessage(
        ax(409, { code: 'duplicate_key', message: 'x' }),
        undefined
      )
    ).toBe(m)
  })
  it('光罩 mock code 重复返回字符串 detail', async () => {
    resetReticleMock()
    const list = await mockReticleApi.list()
    const code = String(list[0].code)
    const e = await mockReticleApi.save(null, { code } as never, 'dup-k1').then(
      () => null,
      (x) => x
    )
    expect(e.response.status).toBe(409)
    expect(e.response.data.detail).toBe(DUPLICATE_KEY_DETAIL)
  })
})
