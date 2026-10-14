import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { mesApi } from '@/lib/api/mes/common'
import { CustomerFields } from './customer'
import {
  customerBody,
  type CustomerDraft,
  customerErrors,
  emptyCustomer,
  ownershipText,
} from './customer-fields'

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

afterEach(async () => {
  vi.restoreAllMocks()
  await i18n.changeLanguage('zh-CN')
})

describe('F6 客户来料字段', () => {
  it('请求体：自有只发 ownership；客户来料带客户、客户批号去首尾空格（D37、D40）', () => {
    expect(customerBody(emptyCustomer())).toEqual({ ownership: 'own' })
    expect(
      customerBody({
        ownership: 'customer',
        customer_id: 'c1',
        customer_label: 'C1',
        customer_lot_no: '  Ab c-1  ',
      })
    ).toEqual({
      ownership: 'customer',
      customer_id: 'c1',
      customer_lot_no: 'Ab c-1',
    })
    expect(customerBody({ ...emptyCustomer(), ownership: 'customer' })).toEqual(
      { ownership: 'customer', customer_lot_no: null }
    )
  })

  it('客户来料未选客户时报错，自有不报', () => {
    expect(customerErrors([emptyCustomer()])).toEqual([])
    expect(
      customerErrors([
        emptyCustomer(),
        { ...emptyCustomer(), ownership: 'customer' },
      ])
    ).toEqual([t('mes.cust.errCustomer', { n: 2 })])
  })

  it('归属文本三语', async () => {
    const info = { ownership: 'customer', customer: 'C1' }
    expect(ownershipText(info)).toBe('客户来料 · C1')
    expect(ownershipText({ ownership: null })).toBe('自有')
    await i18n.changeLanguage('en')
    expect(ownershipText(info)).toBe('Customer-owned · C1')
    await i18n.changeLanguage('ja')
    expect(ownershipText(info)).toBe('顧客支給 · C1')
  })

  it('编辑：切到客户来料出现客户和客户批号，切回自有清空', async () => {
    vi.spyOn(mesApi, 'list').mockResolvedValue({ data: [], count: 0 } as never)
    let last: CustomerDraft = emptyCustomer()
    function Host() {
      const [v, setV] = useState<CustomerDraft>(emptyCustomer())
      last = v
      return (
        <CustomerFields
          value={v}
          onChange={(p) => setV((x) => ({ ...x, ...p }))}
        />
      )
    }
    const s = await render(
      <QueryClientProvider client={new QueryClient()}>
        <Host />
      </QueryClientProvider>
    )
    const own = s.getByLabelText(t('mes.cust.ownership'))
    expect(
      document.querySelector(`[aria-label="${t('mes.cust.lotNo')}"]`)
    ).toBeNull()
    await own.selectOptions('customer')
    const lotNo = s.getByLabelText(t('mes.cust.lotNo'))
    await lotNo.fill('CL-001')
    await expect.poll(() => last.customer_lot_no).toBe('CL-001')
    await own.selectOptions('own')
    await expect.poll(() => last).toEqual(emptyCustomer())
  })
})
