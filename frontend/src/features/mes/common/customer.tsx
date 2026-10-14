/**
 * 客户来料字段（P1 F6 / B7，D36、D37、D40）。
 *
 * - 批次：`customer_lot_no`（客户批号）、`ownership`（own / customer，默认 own）、`customer_id`。
 * - 规则（后端 `customer_start_errors`）：归属为客户来料时必须选客户；自有时不能带客户和客户批号。
 * - 客户批号只去首尾空格，原样保存；查询不区分大小写、精确匹配（D37）。
 */
import { t } from '@/i18n'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { enumLabel } from '@/features/mes/common/labels'
import { RefSelect } from '@/features/mes/common/ref-select'
import {
  type CustomerDraft,
  type CustomerInfo,
  emptyCustomer,
  type Ownership,
  ownershipText,
} from './customer-fields'

/** 批次头部的客户批号与归属标签。 */
export function CustomerBadges({ info }: { info: CustomerInfo }) {
  return (
    <>
      <Badge variant='secondary' data-testid='lot-ownership'>
        {ownershipText(info)}
      </Badge>
      {info.customer_lot_no && (
        <Badge variant='outline' data-testid='lot-customer-lot'>
          {t('mes.cust.lotNo')}: {info.customer_lot_no}
        </Badge>
      )}
    </>
  )
}

/** 开批向导一行里的客户字段编辑（归属 / 客户 / 客户批号）。 */
export function CustomerFields({
  value,
  onChange,
}: {
  value: CustomerDraft
  onChange: (patch: Partial<CustomerDraft>) => void
}) {
  const own = value.ownership === 'own'
  return (
    <div className='flex min-w-[22rem] flex-wrap items-center gap-2'>
      <select
        aria-label={t('mes.cust.ownership')}
        className='h-9 rounded-md border bg-transparent px-2 text-sm'
        value={value.ownership}
        onChange={(e) => {
          const o = e.target.value as Ownership
          // 切回自有时清掉客户字段（后端不允许自有批次带客户）
          onChange(
            o === 'own'
              ? { ...emptyCustomer() }
              : { ownership: 'customer' as const }
          )
        }}
      >
        <option value='own'>{enumLabel('ownership', 'own')}</option>
        <option value='customer'>{enumLabel('ownership', 'customer')}</option>
      </select>
      {!own && (
        <>
          <div className='w-44' aria-label={t('mes.cust.customer')}>
            <RefSelect
              target='customer'
              value={value.customer_id}
              label={value.customer_label}
              onChange={(id, label) =>
                onChange({ customer_id: id, customer_label: label })
              }
            />
          </div>
          <Input
            aria-label={t('mes.cust.lotNo')}
            placeholder={t('mes.cust.lotNo')}
            className='w-36'
            maxLength={100}
            value={value.customer_lot_no}
            onChange={(e) => onChange({ customer_lot_no: e.target.value })}
          />
        </>
      )}
    </div>
  )
}
