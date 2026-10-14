import { AxiosError, AxiosHeaders } from 'axios'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import i18n, { t } from '@/i18n'
import { Toaster } from 'sonner'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { mesApi, type MesEntity } from '@/lib/api/mes/common'
import { SidebarProvider } from '@/components/ui/sidebar'
import type { ListParams } from '@/components/crud'
import { EntityTable } from './entity-table'

// QA P2-1 / P3-3：通过 EntityTable 触发保存，验证 KEYED_ENTITIES 带 key、资质 reason 文案上页面
const ent = (code: string) =>
  ({
    code,
    module: 'execution',
    url: `/mes/${code}`,
    has_code: false,
    tree: false,
    versioned: false,
    readonly: false,
    parent: null,
    children: [],
    label_field: 'note',
    sort_default: 'note',
    natural_key: [],
    read: '',
    write: '',
    can_read: true,
    can_write: true,
    fields: [{ name: 'note', column: 'note', type: 'string' }],
  }) as unknown as MesEntity

const params: ListParams = {
  page: 1,
  pageSize: 20,
  sortOrder: 'asc',
  filters: {},
  q: '',
  query: {},
  setFilter: () => {},
  setRange: () => {},
  set: () => {},
} as unknown as ListParams

function err422(detail: unknown) {
  const e = new AxiosError('422')
  e.response = {
    status: 422,
    data: { detail },
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
  }
  return e
}

async function show(code: string) {
  vi.spyOn(mesApi, 'list').mockResolvedValue({
    data: [{ id: 'r1', note: 'x' }],
    count: 1,
  } as never)
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  qc.setQueryData(['mes', 'meta', 'auto'], {
    modules: [],
    entities: [ent(code)],
    enums: {},
    perms: [],
  })
  const router = createRouter({
    routeTree: createRootRoute({
      component: () => (
        <SidebarProvider>
          <EntityTable entity={ent(code)} params={params} />
          <Toaster />
        </SidebarProvider>
      ),
    }),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  return render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}

const save = async (s: Awaited<ReturnType<typeof show>>) => {
  await s
    .getByRole('button', { name: t('common.edit') })
    .first()
    .click()
  await s.getByRole('button', { name: t('common.save') }).click()
}

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})
afterEach(() => vi.restoreAllMocks())

describe('EntityTable：KEYED_ENTITIES 与资质错误文案', () => {
  it('operator_qual 保存带 Idempotency-Key；self_approval 显示资质文案', async () => {
    const up = vi.spyOn(mesApi, 'update').mockRejectedValue(
      err422([
        {
          loc: ['body', 'approved_by'],
          type: 'value_error',
          code: 'value_error',
          msg: 'approved_by: self approval',
          ctx: { reason: 'self_approval' },
        },
      ])
    )
    const s = await show('operator_qual')
    await save(s)
    await expect.poll(() => up.mock.calls.length).toBe(1)
    const key = up.mock.calls[0][3]
    expect(typeof key).toBe('string')
    expect(key).not.toBe('')
    await expect
      .element(s.getByText(t('mes.qualHistory.err.selfApproval')))
      .toBeInTheDocument()
    // 内容不变重试沿用同一个 key
    await s.getByRole('button', { name: t('common.save') }).click()
    await expect.poll(() => up.mock.calls.length).toBe(2)
    expect(up.mock.calls[1][3]).toBe(key)
  })
  it('非 KEYED 实体不传 key', async () => {
    const up = vi.spyOn(mesApi, 'update').mockResolvedValue({} as never)
    const s = await show('tool')
    await save(s)
    await expect.poll(() => up.mock.calls.length).toBe(1)
    expect(up.mock.calls[0][3]).toBeUndefined()
  })
})
