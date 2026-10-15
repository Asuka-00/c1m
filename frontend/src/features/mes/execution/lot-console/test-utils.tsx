/* eslint-disable react-refresh/only-export-components -- 仅测试使用 */
/** 批次操作台组件测试的公共夹具（预置 `/mes/_meta`、构造执行上下文）。 */
import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ExecContext } from '@/lib/api/mes/execution'

export function makeQc(perms: string[]) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, enabled: false } },
  })
  qc.setQueryData(['mes', 'meta', 'auto'], {
    modules: [],
    entities: [],
    enums: {},
    perms,
  })
  return qc
}

export function Providers({
  qc,
  children,
}: {
  qc: QueryClient
  children: ReactNode
}) {
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

const NEXT: Record<string, string | null> = {
  waiting: 'move_in',
  moved_in: 'track_in',
  running: 'track_out',
  tracked_out: 'move_out',
}

export function execCtx(
  status: string,
  onHold = false,
  over: Partial<ExecContext> = {}
): ExecContext {
  return {
    lot: {
      id: 'L1',
      code: 'LOT1',
      qty: 10,
      lot_status: status,
      on_hold: onHold,
    },
    next_stage: NEXT[status] ?? null,
    tracking_level: 'quantity',
    units: [],
    holds: [],
    reasons: {
      hold: [],
      release: [],
      scrap: [{ id: 'S1', code: 'S1', name: 'S1' }],
      rework: [],
      jump: [],
      bonus: [],
    },
    stack: [],
    exec_ctx: {},
    route_steps: [],
    ...over,
  } as unknown as ExecContext
}
