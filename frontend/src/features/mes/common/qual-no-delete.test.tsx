import { t } from '@/i18n'
import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { RowActions } from '@/components/crud/row-actions'
import { canRemoveRow } from './row-rules'

// 架构师（删除问题）：资质只能停用，表格不显示删除按钮
describe('operator_qual 不显示删除', () => {
  it('规则：operator_qual 不可删，其他实体默认可删', () => {
    expect(canRemoveRow('operator_qual', { id: 'q1' } as never)).toBe(false)
    expect(canRemoveRow('tool', { id: 't1' } as never)).toBe(true)
  })
  it('行操作按规则渲染：资质没有删除按钮', async () => {
    const row = (code: string) => (
      <RowActions
        onEdit={() => {}}
        onDelete={
          canRemoveRow(code, { id: 'x' } as never) ? () => {} : undefined
        }
      />
    )
    const s = await render(
      <>
        <div data-testid='q'>{row('operator_qual')}</div>
        <div data-testid='t'>{row('tool')}</div>
      </>
    )
    await expect
      .element(
        s.getByTestId('q').getByRole('button', { name: t('common.delete') })
      )
      .not.toBeInTheDocument()
    await expect
      .element(
        s.getByTestId('t').getByRole('button', { name: t('common.delete') })
      )
      .toBeInTheDocument()
  })
})
