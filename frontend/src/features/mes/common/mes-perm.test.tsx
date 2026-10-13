import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { render, renderHook } from 'vitest-browser-react'
import { MesCan } from './mes-can'
import { MES_PERM, useMesCan } from './mes-perm'

/** 预置 `/mes/_meta`（租户键默认 'auto'），不发请求。 */
export function withPerms(perms: string[] | null) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, enabled: false } },
  })
  if (perms)
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

describe('useMesCan', () => {
  it('按 _meta.perms 判断权限码', async () => {
    const { result } = await renderHook(() => useMesCan(), {
      wrapper: withPerms([MES_PERM.execHold]),
    })
    expect(result.current(MES_PERM.execHold)).toBe(true)
    expect(result.current(MES_PERM.execWrite)).toBe(false)
  })

  it('元数据未加载时一律无权限', async () => {
    const { result } = await renderHook(() => useMesCan(), {
      wrapper: withPerms(null),
    })
    expect(result.current(MES_PERM.execHold)).toBe(false)
  })
})

describe('MesCan', () => {
  it('有权限渲染子元素，无权限渲染 fallback', async () => {
    const W = withPerms([MES_PERM.execSplit])
    const s = await render(
      <W>
        <MesCan perm={MES_PERM.execSplit}>
          <span>split</span>
        </MesCan>
        <MesCan perm={MES_PERM.execMerge} fallback={<span>no-merge</span>}>
          <span>merge</span>
        </MesCan>
      </W>
    )
    await expect.element(s.getByText('split')).toBeInTheDocument()
    await expect.element(s.getByText('no-merge')).toBeInTheDocument()
    expect(s.container.textContent).toBe('splitno-merge')
  })
})
