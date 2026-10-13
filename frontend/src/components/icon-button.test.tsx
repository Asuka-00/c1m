import i18n from '@/i18n'
import { Pencil } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { IconButton } from './icon-button'

const tip = () =>
  [...document.querySelectorAll('[data-slot=tooltip-content]')]
    .map((x) => x.textContent)
    .join('|')

function Edit({ disabled }: { disabled?: boolean }) {
  const { t } = useTranslation()
  return (
    <IconButton label={t('common.edit')} variant='ghost' disabled={disabled}>
      <Pencil />
    </IconButton>
  )
}

describe('IconButton', () => {
  it('设置 aria-label，悬停时显示提示', async () => {
    const s = await render(<Edit />)
    const b = s.getByRole('button', { name: i18n.t('common.edit') })
    await expect.element(b).toBeVisible()
    expect(b.element().getAttribute('title')).toBeNull()
    await userEvent.hover(b)
    await expect.poll(tip).toContain(i18n.t('common.edit'))
  })

  it('键盘聚焦时也显示提示', async () => {
    await render(<Edit />)
    await userEvent.tab()
    await expect.poll(tip).toContain(i18n.t('common.edit'))
  })

  it('禁用时仍可通过外层包裹悬停显示提示', async () => {
    const s = await render(<Edit disabled />)
    await expect
      .element(s.getByRole('button', { name: i18n.t('common.edit') }))
      .toBeDisabled()
    await userEvent.hover(s.getByTestId('icon-button-disabled-wrap'))
    await expect.poll(tip).toContain(i18n.t('common.edit'))
  })

  it('切换语言后提示与 aria-label 随之变化', async () => {
    const s = await render(<Edit />)
    const ja = i18n.getFixedT('ja')('common.edit')
    expect(ja).not.toBe(i18n.t('common.edit'))
    await i18n.changeLanguage('ja')
    try {
      const b = s.getByRole('button', { name: ja })
      await expect.element(b).toBeVisible()
      await userEvent.hover(b)
      await expect.poll(tip).toContain(ja)
    } finally {
      await i18n.changeLanguage('en')
    }
  })
})
