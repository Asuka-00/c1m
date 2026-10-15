import { AxiosError, AxiosHeaders } from 'axios'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import type { MesEntity } from '@/lib/api/mes/common'
import { NEVER_SUBMIT, toPayload } from '@/features/mes/common/form-payload'
import { mesErrorMessage } from '@/features/mes/common/required'
import { extraFilters } from '@/features/mes/common/use-mes-filters'
import { EXTRA_COLUMNS } from '@/features/mes/registry'

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})
afterEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

const ent = {
  code: 'alarm_code',
  fields: [
    { name: 'alid', column: 'alid', type: 'str' },
    { name: 'action', column: 'action', type: 'enum' },
    // 故意不标 system，验证仍不会提交
    { name: 'migration_note', column: 'migration_note', type: 'text' },
  ],
} as unknown as MesEntity

let n = 0
const cell = async (r: Record<string, unknown>) => {
  const id = `c${n++}`
  const s = await render(
    <div data-testid={id}>
      {EXTRA_COLUMNS.alarm_code[0].cell({ id: 'x', ...r })}
    </div>
  )
  return s.getByTestId(id)
}

describe('报警码 migration_note（OQ-20 / 6d0fbe1）', () => {
  it('列表列已注册；有说明显示「迁移待补配」，悬停 title 为原文', async () => {
    expect(EXTRA_COLUMNS.alarm_code).toHaveLength(1)
    await i18n.changeLanguage('zh-CN')
    const note = '0029: was hold_equipment, no UDT state'
    const el = await cell({ migration_note: note })
    await expect.element(el).toHaveTextContent('迁移待补配')
    expect(
      el
        .element()
        .querySelector('[data-testid=migration-note]')
        ?.getAttribute('title')
    ).toBe(note)
    await expect
      .element(await cell({ migration_note: null }))
      .toHaveTextContent('—')
  })

  it.each(['zh-CN', 'en', 'ja'])('%s 三语文案', async (lng) => {
    await i18n.changeLanguage(lng)
    for (const k of ['col', 'pending', 'none', 'all', 'hint'])
      expect(i18n.exists(`mes.alarmCode.migration.${k}`)).toBe(true)
    expect(i18n.exists('mes.err.readOnlyField')).toBe(true)
    expect(i18n.exists('mes.err.code.read_only_field')).toBe(true)
  })

  it('筛选 ?has_migration_note=true|false', () => {
    const [f] = extraFilters('alarm_code')
    expect(f.name).toBe('has_migration_note')
    expect(
      (f as { options: { value: string }[] }).options.map((o) => o.value)
    ).toEqual(['true', 'false'])
    expect(extraFilters('alarm_log')).toEqual([])
  })

  it('表单不提交 migration_note', () => {
    expect(NEVER_SUBMIT.has('alarm_code.migration_note')).toBe(true)
    const body = toPayload(
      ent,
      { alid: '100', action: 'none', migration_note: 'x' },
      new Set()
    )
    expect(body).toEqual({ alid: '100', action: 'none' })
  })

  it('422 read_only_field 三语', async () => {
    const e = new AxiosError('422')
    e.response = {
      status: 422,
      data: {
        detail: [
          {
            loc: ['body', 'migration_note'],
            msg: 'migration_note: read-only field',
            type: 'read_only_field',
            code: 'read_only_field',
          },
        ],
      },
      statusText: '',
      headers: {},
      config: { headers: new AxiosHeaders() },
    }
    for (const lng of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(lng)
      expect(mesErrorMessage(e, undefined)).toBe(t('mes.err.readOnlyField'))
      expect(mesErrorMessage(e, undefined)).not.toMatch(/read-only field$/)
    }
  })

  it('unknown_field 三语；query 类 loc 不映射到表单字段', async () => {
    const mk = (loc: string[], code: string) => {
      const e = new AxiosError('422')
      e.response = {
        status: 422,
        data: { detail: [{ loc, msg: `${loc[1]}: x`, type: code, code }] },
        statusText: '',
        headers: {},
        config: { headers: new AxiosHeaders() },
      }
      return e
    }
    for (const lng of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(lng)
      expect(mesErrorMessage(mk(['body', 'foo'], 'unknown_field'), ent)).toBe(
        t('mes.err.unknownField')
      )
    }
    await i18n.changeLanguage('zh-CN')
    // body：带字段标签
    expect(
      mesErrorMessage(mk(['body', 'migration_note'], 'read_only_field'), ent)
    ).toContain(': ')
    // query：只前缀参数名，不当作表单字段
    const q = mesErrorMessage(mk(['query', 'alid'], 'unknown_field'), ent)
    expect(q).toBe(`alid: ${t('mes.err.unknownField')}`)
  })
})
