import { act, type ReactNode } from 'react'
import { AxiosError, AxiosHeaders } from 'axios'
import { t } from '@/i18n'
import { toast } from 'sonner'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderHook } from 'vitest-browser-react'
import { execApi } from '@/lib/api/mes/execution'
import { execCtx, makeQc, Providers } from './test-utils'
import { qtimeNotice, useStageRun } from './use-stage-run'

function axErr(status: number, detail: unknown) {
  const e = new AxiosError('fail')
  e.response = {
    status,
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
    data: { detail },
  }
  return e
}

function setup() {
  const qc = makeQc([])
  const inv = vi.spyOn(qc, 'invalidateQueries')
  const wrapper = ({ children }: { children: ReactNode }) => (
    <Providers qc={qc}>{children}</Providers>
  )
  return { inv, wrapper }
}

afterEach(() => vi.restoreAllMocks())

describe('useStageRun', () => {
  it('成功：提示、失效 mes 查询，带强制放行原因时附 override', async () => {
    const stage = vi
      .spyOn(execApi, 'stage')
      .mockResolvedValue({ auto: [], lot: { on_hold: false } } as never)
    const ok = vi.spyOn(toast, 'success')
    const { inv, wrapper } = setup()
    const { result } = await renderHook(
      () => useStageRun(execCtx('waiting'), () => ({ equipment_id: 'E1' })),
      { wrapper }
    )
    await act(async () => {
      await result.current.run.mutateAsync({ override: 'why' })
    })
    expect(stage).toHaveBeenCalledWith('L1', 'move_in', {
      equipment_id: 'E1',
      override: true,
      override_reason: 'why',
    })
    expect(ok).toHaveBeenCalled()
    expect(inv).toHaveBeenCalledWith({ queryKey: ['mes'] })
  })

  it('future hold：警告而非成功提示', async () => {
    vi.spyOn(execApi, 'stage').mockResolvedValue({
      future_hold: [{ comment: 'FH', reason: 'R' }],
    } as never)
    const warn = vi.spyOn(toast, 'warning')
    const ok = vi.spyOn(toast, 'success')
    const { wrapper } = setup()
    const { result } = await renderHook(
      () => useStageRun(execCtx('waiting'), () => ({})),
      { wrapper }
    )
    await act(async () => {
      await result.current.run.mutateAsync({})
    })
    expect(warn).toHaveBeenCalled()
    expect(ok).not.toHaveBeenCalled()
  })

  it('409 check_blocked：记录卡控结果并标记 blocked', async () => {
    const res = [{ check: 'qtime', result: 'block', message: 'x' }]
    vi.spyOn(execApi, 'stage').mockRejectedValue(
      axErr(409, { code: 'check_blocked', results: res })
    )
    const err = vi.spyOn(toast, 'error')
    const { wrapper } = setup()
    const { result } = await renderHook(
      () => useStageRun(execCtx('waiting'), () => ({})),
      { wrapper }
    )
    await act(async () => {
      await result.current.run.mutateAsync({}).catch(() => {})
    })
    expect(result.current.results).toEqual(res)
    expect(result.current.blocked).toBe(true)
    expect(err).toHaveBeenCalledWith(t('mes.exec.blocked'))
  })

  it('其他错误：走 mesErrorMessage（on_hold 本地化）', async () => {
    vi.spyOn(execApi, 'stage').mockRejectedValue(
      axErr(422, [
        {
          loc: ['body', 'on_hold'],
          msg: 'on_hold: lot is on hold; release it first',
        },
      ])
    )
    const err = vi.spyOn(toast, 'error')
    const { wrapper } = setup()
    const { result } = await renderHook(
      () => useStageRun(execCtx('tracked_out', true), () => ({})),
      { wrapper }
    )
    await act(async () => {
      await result.current.run.mutateAsync({}).catch(() => {})
    })
    expect(err).toHaveBeenCalledWith(t('mes.err.code.on_hold'))
    expect(result.current.blocked).toBe(false)
  })

  it('预检：写入结果、不标记 blocked', async () => {
    const res = [{ check: 'c', result: 'pass', message: '' }]
    const pv = vi
      .spyOn(execApi, 'preview')
      .mockResolvedValue({ results: res } as never)
    const { wrapper } = setup()
    const { result } = await renderHook(
      () => useStageRun(execCtx('waiting'), () => ({ equipment_id: 'E' })),
      { wrapper }
    )
    await act(async () => {
      await result.current.preview.mutateAsync()
    })
    expect(pv).toHaveBeenCalledWith('L1', 'move_in', { equipment_id: 'E' })
    expect(result.current.results).toEqual(res)
    expect(result.current.blocked).toBe(false)
  })

  it.each([
    ['waiting', 'move_in'],
    ['moved_in', 'track_in'],
  ])(
    'Q-Time 超时（D22）：%s 批次 %s 返回 200 + qtime=hold → 提示已转 Hold、未执行，并刷新',
    async (status, stage) => {
      const spy = vi.spyOn(execApi, 'stage').mockResolvedValue({
        lot: { id: 'L1', on_hold: true },
        results: [],
        qtime: 'hold',
      } as never)
      const warn = vi.spyOn(toast, 'warning')
      const ok = vi.spyOn(toast, 'success')
      const { inv, wrapper } = setup()
      const { result } = await renderHook(
        () => useStageRun(execCtx(status), () => ({})),
        { wrapper }
      )
      await act(async () => {
        await result.current.run.mutateAsync({})
      })
      expect(spy.mock.calls[0][1]).toBe(stage)
      expect(warn).toHaveBeenCalledWith(qtimeNotice('hold', stage))
      expect(qtimeNotice('hold', stage)).toContain(
        t('mes.exec.qtimeAction.hold')
      )
      expect(ok).not.toHaveBeenCalled()
      expect(inv).toHaveBeenCalledWith({ queryKey: ['mes'] })
    }
  )

  it('已持 Hold 的批次 Track In 返回 422 on_hold：报错并刷新', async () => {
    vi.spyOn(execApi, 'stage').mockRejectedValue(
      axErr(422, {
        code: 'on_hold',
        message: 'lot is on hold; release it first',
      })
    )
    const err = vi.spyOn(toast, 'error')
    const { inv, wrapper } = setup()
    const { result } = await renderHook(
      () => useStageRun(execCtx('moved_in', true), () => ({})),
      { wrapper }
    )
    await act(async () => {
      await result.current.run.mutateAsync({}).catch(() => {})
    })
    expect(err).toHaveBeenCalledWith(t('mes.err.code.on_hold'))
    expect(inv).toHaveBeenCalledWith({ queryKey: ['mes'] })
  })

  it('兼容：422 on_hold 且 message 含 Q-Time 时按已转 Hold 提示', async () => {
    vi.spyOn(execApi, 'stage').mockRejectedValue(
      axErr(422, {
        code: 'on_hold',
        message: 'lot was put on hold: Q-Time expired',
      })
    )
    const warn = vi.spyOn(toast, 'warning')
    const { inv, wrapper } = setup()
    const { result } = await renderHook(
      () => useStageRun(execCtx('moved_in'), () => ({})),
      { wrapper }
    )
    await act(async () => {
      await result.current.run.mutateAsync({}).catch(() => {})
    })
    expect(warn).toHaveBeenCalledWith(qtimeNotice('hold', 'track_in'))
    expect(inv).toHaveBeenCalledWith({ queryKey: ['mes'] })
  })
})
