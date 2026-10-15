import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import i18n, { t } from '@/i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import type { GenealogyLink } from '@/lib/api/mes/execution'
import { GenealogyList } from './split-merge'

const link = (p: Partial<GenealogyLink>): GenealogyLink => ({
  relation: 'split',
  parent_id: 'L1',
  parent: 'LOT1',
  child_id: 'C1',
  child: 'LOT1-B1',
  qty: 10,
  units: [],
  at: null,
  user: null,
  ...p,
})

async function show(lotId: string, links: GenealogyLink[]) {
  const router = createRouter({
    routeTree: createRootRoute({
      component: () => <GenealogyList lotId={lotId} links={links} />,
    }),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  return render(<RouterProvider router={router} />)
}

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

describe('批次谱系关系类型', () => {
  it('relation=transform（单位转换 / 按 bin 拆批）不显示成“合入”', async () => {
    const links = [
      link({ relation: 'transform' }),
      link({ relation: 'merge', child_id: 'M1', child: 'LOT9' }),
    ]
    const s = await show('L1', links)
    const items = s.getByTestId('genealogy').getByRole('listitem')
    await expect
      .element(items.nth(0))
      .toHaveTextContent(t('mes.sm.transformTo'))
    await expect.element(items.nth(1)).toHaveTextContent(t('mes.sm.mergedInto'))
    expect(items.nth(0).element().textContent).not.toContain(
      t('mes.sm.mergedInto')
    )
  })

  it('子批一侧显示“转换自母批”', async () => {
    const s = await show('C1', [link({ relation: 'transform' })])
    await expect
      .element(s.getByTestId('genealogy'))
      .toHaveTextContent(`${t('mes.sm.transformFrom')}LOT1`)
  })
})
