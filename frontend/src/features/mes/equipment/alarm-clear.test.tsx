import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { eqpApi } from '@/lib/api/mes/equipment'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import { makeQc, Providers } from '../execution/lot-console/test-utils'
import { AlarmClearButton } from './alarm-clear'

const row = { id: 'A1', alid: '1001', alarm_status: 'active' }

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})
afterEach(() => vi.restoreAllMocks())

const show = (perms: string[], r: Record<string, unknown> = row) =>
  render(
    <Providers qc={makeQc(perms)}>
      <AlarmClearButton row={r as never} />
    </Providers>
  )

describe('F9 报警履历：清除', () => {
  it('无 mes.alarm:write 或已清除时不显示清除按钮', async () => {
    await show([])
    expect(document.querySelector('[data-testid=alarm-clear]')).toBeNull()
    await show([MES_PERM.alarmWrite], { ...row, alarm_status: 'cleared' })
    expect(document.querySelector('[data-testid=alarm-clear]')).toBeNull()
  })

  it('清除时带备注调用 /alarms/{id}/clear，并提示不自动恢复', async () => {
    const spy = vi
      .spyOn(eqpApi, 'alarmClear')
      .mockResolvedValue({ data: {}, duplicate: false, cleared: true })
    const s = await show([MES_PERM.alarmWrite])
    await s.getByTestId('alarm-clear').click()
    await expect.element(s.getByText(t('mes.alarm.clearDesc'))).toBeVisible()
    await userEvent.fill(s.getByLabelText(t('mes.exec.comment')), ' 已处理 ')
    await s.getByTestId('alarm-clear-ok').click()
    await expect.poll(() => spy.mock.calls.length).toBe(1)
    expect(spy).toHaveBeenCalledWith('A1', { comment: '已处理' })
  })

  it('已清除（cleared=false、data=null）提示未改动；idempotency_key_reused 给三语文案', async () => {
    const { AxiosError, AxiosHeaders } = await import('axios')
    const { toast } = await import('sonner')
    const info = vi.spyOn(toast, 'info')
    const error = vi.spyOn(toast, 'error')
    const spy = vi.spyOn(eqpApi, 'alarmClear').mockResolvedValueOnce({
      data: null as never,
      duplicate: false,
      cleared: false,
    })
    const s = await show([MES_PERM.alarmWrite])
    await s.getByTestId('alarm-clear').click()
    await s.getByTestId('alarm-clear-ok').click()
    await expect.poll(() => info.mock.calls.length).toBe(1)
    expect(info).toHaveBeenCalledWith(t('mes.alarm.already'))
    const e = new AxiosError('422')
    e.response = {
      status: 422,
      data: { detail: { code: 'idempotency_key_reused', message: 'x' } },
      statusText: '',
      headers: {},
      config: { headers: new AxiosHeaders() },
    }
    spy.mockRejectedValueOnce(e)
    await s.getByTestId('alarm-clear').click()
    await s.getByTestId('alarm-clear-ok').click()
    await expect.poll(() => error.mock.calls.length).toBe(1)
    expect(error).toHaveBeenCalledWith(t('mes.err.code.idempotency_key_reused'))
  })
})
