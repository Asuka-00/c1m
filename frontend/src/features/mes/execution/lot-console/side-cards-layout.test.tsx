import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n, { LANGUAGES } from '@/i18n'
import '@/styles/index.css'
import { afterAll, describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { page } from 'vitest/browser'
import type { ExecContext } from '@/lib/api/mes/execution'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import { WipActionsCard } from '../dispatch/wip-actions'
import { SplitMergeCard } from '../split-merge'
import { HoldCard } from './hold-card'

const cx = {
  lot: {
    id: 'L1',
    code: 'LOT1',
    qty: 25,
    lot_status: 'waiting',
    on_hold: false,
  },
  next_stage: 'move_in',
  tracking_level: 'wafer',
  units: [],
  holds: [],
  reasons: {
    hold: [],
    release: [],
    scrap: [],
    rework: [],
    jump: [],
    bonus: [],
  },
  stack: [],
  exec_ctx: {},
  route_steps: [
    { id: 'S1', seq: 1, operation: null },
    { id: 'S2', seq: 2, operation: null },
  ],
  sm: {
    allowed: true,
    rule: { code: 'SM-1', allow_split: true, allow_merge: true },
    candidates: [],
    genealogy: [],
    priority: null,
  },
} as unknown as ExecContext

const qc = new QueryClient({
  defaultOptions: { queries: { retry: false, enabled: false } },
})
qc.setQueryData(['mes', 'meta', 'auto'], {
  modules: [],
  entities: [],
  enums: {},
  perms: Object.values(MES_PERM),
})

function Cards() {
  const box = (c: ReactNode) => <div style={{ width: 340 }}>{c}</div>
  return (
    <QueryClientProvider client={qc}>
      <div className='space-y-4'>
        {box(<HoldCard cx={cx} />)}
        {box(<SplitMergeCard cx={cx} />)}
        {box(<WipActionsCard cx={cx} />)}
      </div>
    </QueryClientProvider>
  )
}

describe('批次操作台侧栏卡片标题', () => {
  afterAll(() => i18n.changeLanguage('en'))

  it.each(LANGUAGES)('%s：340px 宽时标题不折行', async (lng) => {
    await i18n.changeLanguage(lng)
    const r = await render(<Cards />)
    const titles = [
      ...r.container.querySelectorAll('[data-slot=card-title] span'),
    ]
    expect(titles.length).toBe(3)
    for (const el of titles) {
      const lh = parseFloat(getComputedStyle(el).lineHeight) || 24
      expect(el.getBoundingClientRect().height).toBeLessThanOrEqual(lh + 1)
    }
    if (import.meta.env.VITE_SHOT)
      await page.screenshot({ path: `/tmp/c1m-shot/side-${lng}.png` })
  })
})
