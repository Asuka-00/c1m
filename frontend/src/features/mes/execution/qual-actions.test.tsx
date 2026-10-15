import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { t } from '@/i18n'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { mesApi } from '@/lib/api/mes/common'
import { TooltipProvider } from '@/components/ui/tooltip'
import {
  qualActionBody,
  qualActionErrors,
  qualExpiresUnchanged,
} from './qual-action-rules'
import { QualActions } from './qual-actions'

const V = { expires_on: '', reason_id: '', comment: '', approved_by: '' }

describe('资质行操作规则（B6 / D88）', () => {
  it('必填：停用 reason+comment；改有效期另要 approved_by；恢复不要', () => {
    expect(Object.keys(qualActionErrors('deactivate', V)).sort()).toEqual([
      'comment',
      'reason_id',
    ])
    expect(Object.keys(qualActionErrors('renew', V)).sort()).toEqual([
      'approved_by',
      'comment',
      'reason_id',
    ])
    expect(qualActionErrors('reactivate', V)).toEqual({})
  })
  it('请求体：停用与改有效期分开；空到期日 = 永久 null', () => {
    const v = { ...V, reason_id: 'R', comment: ' c ', approved_by: 'lead' }
    expect(qualActionBody('deactivate', v)).toEqual({
      is_active: false,
      reason_id: 'R',
      comment: 'c',
    })
    expect(qualActionBody('renew', v)).toEqual({
      expires_on: null,
      reason_id: 'R',
      comment: 'c',
      approved_by: 'lead',
    })
    expect(
      qualActionBody('renew', { ...v, expires_on: '2026-10-01' })
    ).toMatchObject({
      expires_on: '2026-10-01',
    })
    expect(qualActionBody('reactivate', v)).toEqual({ is_active: true })
  })
})

const wrap = (row: Record<string, unknown>, canWrite = true) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  qc.setQueryData(['mes', 'meta', 'auto'], {
    modules: [],
    entities: [
      {
        code: 'operator_qual',
        can_write: canWrite,
        can_read: true,
        fields: [],
      },
    ],
    enums: {},
    perms: [],
  })
  return (
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <QualActions row={row as never} />
      </TooltipProvider>
    </QueryClientProvider>
  )
}
afterEach(() => vi.restoreAllMocks())

describe('QA P3-2 有效期未改禁止保存', () => {
  it('规则：相同日期 / 原永久仍留空 = 未改', () => {
    expect(qualExpiresUnchanged('2026-12-31', '2026-12-31')).toBe(true)
    expect(qualExpiresUnchanged(null, '')).toBe(true)
    expect(qualExpiresUnchanged(undefined, '')).toBe(true)
    expect(qualExpiresUnchanged(null, '2026-12-31')).toBe(false)
    expect(qualExpiresUnchanged('2026-12-31', '')).toBe(false)
  })
  it.each([
    ['定期', '2026-12-31', '2026-11-01'],
    ['永久', null, '2026-11-01'],
  ])('页面（原%s）：未改时保存禁用并提示，改后可用', async (_n, exp, next) => {
    vi.spyOn(mesApi, 'list').mockResolvedValue({ data: [], count: 0 } as never)
    const s = await render(wrap({ id: 'q1', is_active: true, expires_on: exp }))
    await s.getByTestId('qual-act-renew').click()
    await expect.element(s.getByTestId('qual-action-submit')).toBeDisabled()
    await expect
      .element(s.getByTestId('qual-expires-unchanged'))
      .toHaveTextContent(t('mes.qualAction.expiresUnchanged'))
    await s.getByLabelText(t('mes.qualHistory.field.expires_on')).fill(next)
    await expect.element(s.getByTestId('qual-action-submit')).toBeEnabled()
    await expect
      .element(s.getByTestId('qual-expires-unchanged'))
      .not.toBeInTheDocument()
  })
})

describe('资质行操作页面', () => {
  it('改有效期（缩短）：带 key 与 approved_by 走 PATCH', async () => {
    vi.spyOn(mesApi, 'list').mockResolvedValue({
      data: [{ id: 'R1', code: 'Q-RENEW', name: '复训' }],
      count: 1,
    } as never)
    const up = vi.spyOn(mesApi, 'update').mockResolvedValue({} as never)
    const s = await render(
      wrap({ id: 'q1', is_active: true, expires_on: '2026-12-31' })
    )
    await s.getByTestId('qual-act-renew').click()
    await s
      .getByLabelText(t('mes.qualHistory.field.expires_on'))
      .fill('2026-11-01')
    await s.getByRole('combobox').selectOptions('R1')
    await s
      .getByLabelText(new RegExp(t('mes.qualHistory.col.comment')))
      .fill('shorten')
    await s
      .getByLabelText(new RegExp(t('mes.qualHistory.col.approvedBy')))
      .fill('lead')
    await s.getByTestId('qual-action-submit').click()
    await expect.poll(() => up.mock.calls.length).toBe(1)
    const [code, id, body, key] = up.mock.calls[0]
    expect([code, id]).toEqual(['operator_qual', 'q1'])
    expect(body).toEqual({
      expires_on: '2026-11-01',
      reason_id: 'R1',
      comment: 'shorten',
      approved_by: 'lead',
    })
    expect(typeof key).toBe('string')
  })
  it('停用中只显示恢复；无写权限不显示', async () => {
    const s = await render(wrap({ id: 'q1', is_active: false }))
    await expect
      .element(s.getByTestId('qual-act-reactivate'))
      .toBeInTheDocument()
    await expect
      .element(s.getByTestId('qual-act-deactivate'))
      .not.toBeInTheDocument()
  })
  it('无写权限不显示任何操作', async () => {
    const s = await render(wrap({ id: 'q1', is_active: true }, false))
    await expect
      .element(s.getByTestId('qual-act-renew'))
      .not.toBeInTheDocument()
  })
})
