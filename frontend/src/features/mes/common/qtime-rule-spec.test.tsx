import { AxiosError, AxiosHeaders } from 'axios'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { t } from '@/i18n'
import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { mesApi, type MesEntity, type MesField } from '@/lib/api/mes/common'
import { EntityForm } from './entity-form'
import { fieldHelp } from './labels'
import { mesErrorMessage, requiredBy, validateRequired } from './required'

const f = (x: Partial<MesField>) =>
  ({ required: false, required_when: null, help: false, ...x }) as MesField
// 与后端 463d599 qtime_rule 规格一致（D24/D25/D26）
const action = f({
  name: 'action',
  column: 'action',
  type: 'enum',
  enum: 'qtime_action',
  required: true,
})
const reason = f({
  name: 'reason',
  column: 'reason_id',
  type: 'ref',
  ref: 'reason_code',
  help: true,
})
const isActive = f({ name: 'is_active', column: 'is_active', type: 'bool' })
const activeSince = f({
  name: 'active_since',
  column: 'active_since',
  type: 'datetime',
  system: true,
})
const rule = {
  code: 'qtime_rule',
  fields: [action, reason, isActive, activeSince],
} as unknown as MesEntity

async function showForm(entity: MesEntity, row: Record<string, unknown>) {
  vi.spyOn(mesApi, 'meta').mockResolvedValue({
    enums: { qtime_action: ['warn', 'hold', 'rework'] },
  } as never)
  vi.spyOn(mesApi, 'attrs').mockResolvedValue([] as never)
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <EntityForm
        entity={entity}
        row={row as never}
        open
        onOpenChange={() => {}}
        onSubmit={async () => {}}
      />
    </QueryClientProvider>
  )
}

describe('Q-Time 规则（后端 463d599 规格）', () => {
  it('hold 时原因码选填，且显示 qtime_expired 帮助文本', () => {
    const v = { action: 'hold', reason_id: null, is_active: true }
    expect(requiredBy(rule, reason, v)).toBeNull()
    expect(validateRequired(rule, v, new Set())).toEqual({})
    expect(fieldHelp(rule, reason)).toContain('qtime_expired')
  })

  it('RC-07：原因码不存在 / 属于其他租户时，照常显示后端 422', () => {
    const e = new AxiosError('Request failed')
    e.response = {
      status: 422,
      statusText: '',
      headers: {},
      config: { headers: new AxiosHeaders() },
      data: {
        detail: [
          {
            loc: ['body', 'reason_id'],
            msg: 'reason: not found',
            type: 'value_error',
          },
        ],
      },
    }
    const msg = mesErrorMessage(e, rule)
    expect(msg).toBeTruthy()
    expect(msg).toContain('not found')
  })

  it('422 qtime_action_invalid {code, message, action} 按 code 本地化', () => {
    const e = new AxiosError('Request failed')
    e.response = {
      status: 422,
      statusText: '',
      headers: {},
      config: { headers: new AxiosHeaders() },
      data: {
        detail: {
          code: 'qtime_action_invalid',
          message: "Q-Time action 'scrap' is no longer supported",
          action: 'scrap',
        },
      },
    }
    expect(mesErrorMessage(e, rule)).toBe(
      t('mes.err.code.qtime_action_invalid')
    )
  })

  it('审计动作 qtime_rework 与字段标签已本地化', () => {
    expect(t('mes.enum.audit_action.qtime_rework')).toContain('Q-Time')
    expect(t('mes.field.qtime_rule.is_active')).not.toBe('is_active')
    expect(t('mes.field.qtime_rule.active_since')).not.toBe('active_since')
  })

  it('其他实体：布尔字段仍为复选框，系统字段编辑时不显示', async () => {
    const other = {
      code: 'other',
      fields: [isActive, activeSince],
    } as unknown as MesEntity
    const s = await showForm(other, {
      id: 'X1',
      is_active: true,
      active_since: '2026-10-13T12:00:00+00:00',
    })
    await expect.element(s.getByRole('checkbox')).toBeChecked()
    expect(document.querySelector('[role=switch]')).toBeNull()
    expect(document.querySelector('[data-testid=ro-active_since]')).toBeNull()
  })

  it('编辑表单：动作选项按后端枚举（无 scrap），is_active 为开关，active_since 只读', async () => {
    vi.spyOn(mesApi, 'meta').mockResolvedValue({
      enums: { qtime_action: ['warn', 'hold', 'rework'] },
    } as never)
    vi.spyOn(mesApi, 'attrs').mockResolvedValue([] as never)
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const s = await render(
      <QueryClientProvider client={qc}>
        <EntityForm
          entity={rule}
          row={
            {
              id: 'R1',
              action: 'hold',
              reason_id: null,
              is_active: true,
              active_since: '2026-10-13T12:00:00+00:00',
            } as never
          }
          open
          onOpenChange={() => {}}
          onSubmit={async () => {}}
        />
      </QueryClientProvider>
    )
    await expect
      .element(
        s.getByRole('switch', { name: t('mes.field.qtime_rule.is_active') })
      )
      .toBeChecked()
    await expect.element(s.getByTestId('ro-active_since')).toBeVisible()
    expect(document.querySelector('#f-active_since')).toBeNull()
    await s
      .getByRole('combobox', { name: t('mes.field.qtime_rule.action') })
      .click()
    const opts = [...document.querySelectorAll('[role=option]')].map(
      (o) => o.textContent
    )
    expect(opts).toEqual(
      ['warn', 'hold', 'rework'].map((x) => t(`mes.enum.qtime_action.${x}`))
    )
  })
})
