import { AxiosError, AxiosHeaders } from 'axios'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { t } from '@/i18n'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { mesApi } from '@/lib/api/mes/common'
import { mountApi, type MountRow } from '@/lib/api/mes/equipment'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import { MountDialog, mountErrorMessage } from './mount-dialog'

const EQ = { id: 'eq-1', code: 'DS01' }
const row: MountRow = {
  id: 'm-1',
  equipment_id: EQ.id,
  port_code: 'LP1',
  material_lot_code: 'ML-001',
  material_lot_id: 'ml-1',
  mounted_at: '2026-10-14T02:00:00Z',
  unmounted_at: null,
  source: 'manual',
  mounted_by: 'op',
  comment: null,
}

function setup(perms: string[], ports: string[] = ['LP1', 'LP2']) {
  vi.spyOn(mesApi, 'list').mockResolvedValue({
    data: ports.map((code) => ({ id: code, code })),
    count: ports.length,
  } as never)
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  qc.setQueryDefaults(['mes', 'meta'], { staleTime: Infinity })
  qc.setQueryData(['mes', 'meta', 'auto'], {
    modules: [],
    entities: [],
    enums: {},
    perms,
  })
  return render(
    <QueryClientProvider client={qc}>
      <MountDialog eq={EQ} onClose={() => {}} />
    </QueryClientProvider>
  )
}

function err409(detail: Record<string, unknown>) {
  const e = new AxiosError('conflict')
  e.response = {
    status: 409,
    data: { detail },
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
  }
  return e
}

afterEach(() => vi.restoreAllMocks())

describe('机台上料对话框（F2）', () => {
  it('列出在装的料；上料只传可写字段，事件号是 UUID，不传 source', async () => {
    vi.spyOn(mountApi, 'at').mockResolvedValue([row])
    const mount = vi
      .spyOn(mountApi, 'mount')
      .mockResolvedValue({ data: row, duplicate: true })
    const screen = await setup([MES_PERM.equipmentMount])
    await expect.element(screen.getByText('ML-001')).toBeVisible()
    await screen.getByRole('combobox').click()
    await screen.getByRole('option', { name: 'LP2' }).click()
    await userEvent.fill(screen.getByLabelText(t('mes.mount.lot')), ' ML-002 ')
    await screen
      .getByRole('button', { name: t('mes.mount.submit'), exact: true })
      .click()
    await vi.waitFor(() => expect(mount).toHaveBeenCalledOnce())
    const [eqId, body] = mount.mock.calls[0]
    expect(eqId).toBe(EQ.id)
    expect(Object.keys(body).sort()).toEqual([
      'comment',
      'external_event_id',
      'material_lot_code',
      'port_code',
    ])
    expect(body).toMatchObject({
      port_code: 'LP2',
      material_lot_code: 'ML-002',
    })
    expect(body.external_event_id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
    )
  })

  it('机台没有装载口子单元时，上料口是文本框', async () => {
    vi.spyOn(mountApi, 'at').mockResolvedValue([])
    const screen = await setup([MES_PERM.equipmentMount], [])
    await expect.element(screen.getByText(t('mes.mount.empty'))).toBeVisible()
    await expect
      .element(screen.getByLabelText(t('mes.mount.port')))
      .toBeVisible()
    expect(screen.getByLabelText(t('mes.mount.port')).element().tagName).toBe(
      'INPUT'
    )
  })

  it('没有 mes.equipment:mount 权限时上料和卸料按钮都不可用', async () => {
    vi.spyOn(mountApi, 'at').mockResolvedValue([row])
    const screen = await setup([])
    await expect
      .element(screen.getByRole('button', { name: t('mes.mount.unmount') }))
      .toBeDisabled()
    await expect
      .element(
        screen.getByRole('button', { name: t('mes.mount.submit'), exact: true })
      )
      .toBeDisabled()
  })

  it('改上料口或物料批会换事件号；什么都不改直接重试沿用原事件号', async () => {
    vi.spyOn(mountApi, 'at').mockResolvedValue([])
    const mount = vi
      .spyOn(mountApi, 'mount')
      .mockRejectedValue(new AxiosError('timeout', 'ECONNABORTED'))
    const screen = await setup([MES_PERM.equipmentMount])
    const submit = screen.getByRole('button', {
      name: t('mes.mount.submit'),
      exact: true,
    })
    const ids = () => mount.mock.calls.map(([, body]) => body.external_event_id)
    await screen.getByRole('combobox').click()
    await screen.getByRole('option', { name: 'LP1' }).click()
    await userEvent.fill(screen.getByLabelText(t('mes.mount.lot')), 'ML01')
    await submit.click()
    await vi.waitFor(() => expect(mount).toHaveBeenCalledTimes(1))
    // 超时后原样重试：同一事件号
    await submit.click()
    await vi.waitFor(() => expect(mount).toHaveBeenCalledTimes(2))
    expect(ids()[1]).toBe(ids()[0])
    // 改物料批：新事件号
    await userEvent.fill(screen.getByLabelText(t('mes.mount.lot')), 'ML05')
    await submit.click()
    await vi.waitFor(() => expect(mount).toHaveBeenCalledTimes(3))
    expect(ids()[2]).not.toBe(ids()[1])
    // 改上料口：再换新事件号
    await screen.getByRole('combobox').click()
    await screen.getByRole('option', { name: 'LP2' }).click()
    await submit.click()
    await vi.waitFor(() => expect(mount).toHaveBeenCalledTimes(4))
    expect(ids()[3]).not.toBe(ids()[2])
    expect(new Set(ids()).size).toBe(3)
    expect(mount.mock.calls[3][1]).toMatchObject({
      port_code: 'LP2',
      material_lot_code: 'ML05',
    })
  })

  it('409 错误码翻译成提示', () => {
    expect(
      mountErrorMessage(
        err409({
          code: 'port_occupied',
          port_code: 'LP1',
          current_material_lot_code: 'ML-001',
        })
      )
    ).toBe(t('mes.mount.portOccupied', { port: 'LP1', lot: 'ML-001' }))
    expect(mountErrorMessage(err409({ code: 'already_unmounted' }))).toBe(
      t('mes.mount.alreadyUnmounted')
    )
  })
})
