import { AxiosError, AxiosHeaders } from 'axios'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { mesErrorMessage } from '@/features/mes/common/required'
import { codeItemText, errorMessage } from './client'

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
const item = (
  code: string,
  ctx?: Record<string, unknown>,
  loc = ['query', 'x'],
  msg = 'backend msg'
) => ({ loc, msg, type: code, code, ...(ctx ? { ctx } : {}) })

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})
afterEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

describe('1a7c0fb 固定码 + ctx 插值', () => {
  it.each(['zh-CN', 'en', 'ja'])('%s 每个码都有文案', async (lng) => {
    await i18n.changeLanguage(lng)
    for (const c of [
      'date_range_too_large',
      'date_range_too_large_nolimit',
      'timezone_required',
      'unknown_columns',
      'no_conversion_path',
      'ref_not_found',
      'enum',
      'step_ids_mismatch',
      'not_text_filter',
    ])
      expect(i18n.exists(`mes.err.code.${c}`)).toBe(true)
  })

  it('date_range_too_large 按 max_days，没有时不带天数', () => {
    expect(codeItemText(item('date_range_too_large', { max_days: 366 }))).toBe(
      '日期跨度最多 366 天，请缩小范围。'
    )
    const none = codeItemText(item('date_range_too_large'))
    expect(none).toBe(t('mes.err.code.date_range_too_large_nolimit'))
    expect(none).not.toMatch(/\d/)
  })

  it('timezone_required / step_ids_mismatch；date_range_invalid 已退役（D77 补充二）', () => {
    expect(i18n.exists('mes.err.code.date_range_invalid')).toBe(false)
    for (const c of ['timezone_required', 'step_ids_mismatch'])
      expect(errorMessage(ax([item(c)]))).toBe(t(`mes.err.code.${c}`))
  })

  it('unknown_columns 列出 ctx.columns', async () => {
    const e = ax([
      item('unknown_columns', { columns: ['foo', 'bar'] }, ['body', 'file']),
    ])
    expect(mesErrorMessage(e, undefined)).toBe(
      '导入文件有无法识别的列：foo、bar'
    )
    await i18n.changeLanguage('en')
    expect(errorMessage(e)).toContain('foo, bar')
  })

  it('no_conversion_path 带 from_uom / to_uom', () => {
    expect(
      codeItemText(
        item('no_conversion_path', { from_uom: 'kg', to_uom: 'pcs' })
      )
    ).toBe('没有从 kg 到 pcs 的换算关系。')
  })

  it('ref_not_found 用实体名', () => {
    expect(
      codeItemText(item('ref_not_found', { entity: 'uom' }, ['body', 'uom_id']))
    ).toBe(`找不到对应的${t('mes.entity.uom')}。`)
    expect(codeItemText(item('ref_not_found', { entity: 'zzz' }))).toContain(
      'zzz'
    )
  })

  it('enum 列出 expected（数组或字符串）', () => {
    expect(codeItemText(item('enum', { expected: ['lot', 'wafer'] }))).toBe(
      '取值无效，可选：lot、wafer'
    )
    expect(codeItemText(item('enum', { expected: "'a' or 'b'" }))).toContain(
      "'a' or 'b'"
    )
  })

  it('not_text_filter 带 field（path 类 loc）', () => {
    expect(
      errorMessage(
        ax([item('not_text_filter', { field: 'qty' }, ['path', 'field'])])
      )
    ).toBe('qty 不是可筛选的文本字段')
  })

  it('value_error 兜底显示后端 msg', () => {
    expect(codeItemText(item('value_error'))).toBeNull()
    expect(
      errorMessage(
        ax([item('value_error', undefined, ['query', 'x'], 'x: bad thing')])
      )
    ).toBe('x: bad thing')
  })
})
