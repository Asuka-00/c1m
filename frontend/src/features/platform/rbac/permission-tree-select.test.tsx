import { t } from '@/i18n'
import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import type { PermNode } from '@/lib/api'
import { PermissionTreeSelect } from './permission-tree-select'

const node = (x: Partial<PermNode>) =>
  ({
    kind: 'perm',
    type: 'button',
    key: null,
    path: null,
    icon: null,
    component: null,
    sort_order: 0,
    visible: true,
    status: 'active',
    scope: null,
    space: null,
    children: [],
    ...x,
  }) as PermNode

const tip = () =>
  [...document.querySelectorAll('[data-slot=tooltip-content]')]
    .map((x) => x.textContent)
    .join('|')

describe('PermissionTreeSelect 展开 / 收起按钮', () => {
  it('悬停显示与 aria-label 一致的提示，切换后文案随之变化', async () => {
    const tree = [
      node({
        id: 'M1',
        kind: 'menu',
        name: 'Menu',
        code: 'menu',
        children: [node({ id: 'P1', name: 'Read', code: 'x:read' })],
      }),
    ]
    const s = await render(
      <PermissionTreeSelect nodes={tree} value={[]} onChange={() => {}} />
    )
    const b = s
      .getByRole('treeitem')
      .getByRole('button', { name: t('common.collapse') })
    await userEvent.hover(b)
    await expect.poll(tip).toContain(t('common.collapse'))
    await b.click()
    const e = s
      .getByRole('treeitem')
      .getByRole('button', { name: t('common.expand') })
    await expect.element(e).toBeVisible()
    await userEvent.unhover(e)
    await userEvent.hover(e)
    await expect.poll(tip).toContain(t('common.expand'))
  })
})
