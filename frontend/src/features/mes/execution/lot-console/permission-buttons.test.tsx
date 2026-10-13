import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import type { ExecContext } from '@/lib/api/mes/execution'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import { SplitMergeCard } from '../split-merge'
import { WipActionsCard } from '../wip-actions'
import { HoldCard } from './hold-card'

function wrap(perms: string[]) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, enabled: false } },
  })
  qc.setQueryData(['mes', 'meta', 'auto'], {
    modules: [],
    entities: [],
    enums: {},
    perms,
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

const hold = {
  id: 'H1',
  reason_label: 'QC',
  hold_type: 'manual',
  held_at: '2026-10-13T00:00:00Z',
  is_active: true,
}

function cx(status: string, onHold = false, holds = onHold ? [hold] : []) {
  return {
    lot: {
      id: 'L1',
      code: 'LOT1',
      qty: 25,
      lot_status: status,
      on_hold: onHold,
    },
    next_stage: status === 'waiting' ? 'move_in' : null,
    tracking_level: 'wafer',
    units: [],
    holds,
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
      rule: { allow_split: true, allow_merge: true },
      candidates: [],
      genealogy: [],
      priority: null,
    },
  } as unknown as ExecContext
}

const ALL = Object.values(MES_PERM)

async function renderIn(
  W: (p: { children: ReactNode }) => ReactNode,
  el: ReactNode
) {
  return render(<W>{el}</W>)
}

describe('批次操作台按钮权限', () => {
  it('无 mes.exec:hold 时不显示 Hold / Release 按钮', async () => {
    const W = wrap([])
    const s = await render(
      <W>
        <HoldCard cx={cx('waiting', true)} />
      </W>
    )
    expect(s.container.querySelector('[data-testid=open-hold]')).toBeNull()
    expect(s.container.querySelector('[data-testid=open-release]')).toBeNull()
  })

  it('有权限时显示 Hold / Release；终态批次不显示 Hold，仍可 Release', async () => {
    const W = wrap(ALL)
    const live = await render(
      <W>
        <HoldCard cx={cx('waiting', true)} />
      </W>
    )
    expect(
      live.container.querySelector('[data-testid=open-hold]')
    ).not.toBeNull()
    expect(
      live.container.querySelector('[data-testid=open-release]')
    ).not.toBeNull()
    await live.unmount()
    const done = await render(
      <W>
        <HoldCard cx={cx('scrapped', true)} />
      </W>
    )
    expect(done.container.querySelector('[data-testid=open-hold]')).toBeNull()
    expect(
      done.container.querySelector('[data-testid=open-release]')
    ).not.toBeNull()
  })

  it('拆合批：无权限禁用；Hold 中可拆批不可合批；running 都不可', async () => {
    const none = await renderIn(wrap([]), <SplitMergeCard cx={cx('waiting')} />)
    await expect.element(none.getByTestId('open-split')).toBeDisabled()
    await expect.element(none.getByTestId('open-merge')).toBeDisabled()
    await none.unmount()

    const held = await renderIn(
      wrap(ALL),
      <SplitMergeCard cx={cx('waiting', true)} />
    )
    await expect.element(held.getByTestId('open-split')).toBeEnabled()
    await expect.element(held.getByTestId('open-merge')).toBeDisabled()
    await held.unmount()

    const running = await renderIn(
      wrap(ALL),
      <SplitMergeCard cx={cx('running')} />
    )
    await expect.element(running.getByTestId('open-split')).toBeDisabled()
    await expect.element(running.getByTestId('open-merge')).toBeDisabled()
  })

  it('在制调整：按 jump / adjust 权限与状态启用', async () => {
    const none = await renderIn(wrap([]), <WipActionsCard cx={cx('waiting')} />)
    for (const id of ['open-jump', 'open-adjust', 'open-priority'])
      await expect.element(none.getByTestId(id)).toBeDisabled()
    await none.unmount()

    const held = await renderIn(
      wrap(ALL),
      <WipActionsCard cx={cx('waiting', true)} />
    )
    await expect.element(held.getByTestId('open-jump')).toBeDisabled()
    await expect.element(held.getByTestId('open-adjust')).toBeEnabled()
    await expect.element(held.getByTestId('open-priority')).toBeEnabled()
  })

  it('M2：completed / stored 批次可 Hold，merged 不可', async () => {
    const W = wrap(ALL)
    for (const [st, shown] of [
      ['completed', true],
      ['stored', true],
      ['merged', false],
    ] as const) {
      const r = await render(
        <W>
          <HoldCard cx={cx(st)} />
        </W>
      )
      expect(!!r.container.querySelector('[data-testid=open-hold]')).toBe(shown)
      await r.unmount()
    }
  })
})
