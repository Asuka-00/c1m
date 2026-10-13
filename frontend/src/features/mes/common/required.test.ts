import { AxiosError, AxiosHeaders } from 'axios'
import { t } from '@/i18n'
import { describe, expect, it } from 'vitest'
import type { MesEntity } from '@/lib/api/mes/common'
import { enumLabel } from './labels'
import { mesCodeMessage, mesErrorMessage } from './required'

function axErr(status: number, detail: unknown) {
  const e = new AxiosError('Request failed')
  e.response = {
    status,
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
    data: { detail },
  }
  return e
}
const field = (f: string, msg: string) => [
  { loc: ['body', f], msg, type: 'value_error' },
]
const lotE = { code: 'lot', fields: [] } as unknown as MesEntity

describe('mesErrorMessage：N5 对象格式', () => {
  it('on_hold / lot_status 按 code 识别，lot_status 用 action 与状态生成提示', () => {
    expect(
      mesErrorMessage(
        axErr(422, {
          code: 'on_hold',
          message: 'lot is on hold',
          action: 'move_out',
        }),
        lotE
      )
    ).toBe(t('mes.err.code.on_hold'))
    expect(
      mesErrorMessage(
        axErr(422, {
          code: 'lot_status',
          action: 'track_in',
          lot_status: 'waiting',
        }),
        undefined
      )
    ).toBe(
      t('mes.err.code.lot_status_stage', {
        stage: t('mes.exec.stage.track_in'),
        status: enumLabel('lot_status', 'waiting'),
      })
    )
    expect(
      mesErrorMessage(
        axErr(422, {
          code: 'lot_status',
          action: 'hold',
          lot_status: 'scrapped',
        }),
        lotE
      )
    ).toBe(
      t('mes.err.code.lot_status_is', {
        status: enumLabel('lot_status', 'scrapped'),
      })
    )
    expect(mesErrorMessage(axErr(422, { code: 'lot_status' }), lotE)).toBe(
      t('mes.err.code.lot_status')
    )
  })

  it('merge_source_invalid 优先按 code，即使 message 不含关键词', () => {
    expect(
      mesErrorMessage(
        axErr(422, {
          code: 'merge_source_invalid',
          message: 'bad sources',
          duplicates: ['L2'],
          includes_target: false,
        }),
        lotE
      )
    ).toBe(t('mes.err.code.merge_source_invalid'))
  })

  it('D24：删除被 Hold 引用的 Q-Time 规则返回 409 qtime_rule_in_use，提示改为停用', () => {
    expect(
      mesErrorMessage(
        axErr(409, {
          code: 'qtime_rule_in_use',
          message: 'qtime rule is referenced by holds',
        }),
        { code: 'qtime_rule', fields: [] } as unknown as MesEntity
      )
    ).toBe(t('mes.err.code.qtime_rule_in_use'))
  })

  it('幂等键错误码只认 detail.code，裸字符串不当作错误码', () => {
    expect(mesCodeMessage(axErr(409, 'idempotency_in_progress'))).toBeNull()
    expect(
      mesCodeMessage(axErr(409, { code: 'idempotency_in_progress' }))
    ).toBe(t('mes.err.code.idempotency_in_progress'))
  })
})

describe('mesErrorMessage：旧格式兜底（后端按 N5 落地后可删）', () => {
  it('on_hold（422 字段错误）', () => {
    const e = axErr(
      422,
      field('on_hold', 'on_hold: lot is on hold; release it first')
    )
    expect(mesErrorMessage(e, lotE)).toBe(t('mes.err.code.on_hold'))
    expect(mesErrorMessage(e, undefined)).toBe(t('mes.err.code.on_hold'))
  })

  it('lot_status：解析阶段与状态', () => {
    expect(
      mesErrorMessage(
        axErr(
          422,
          field('lot_status', 'lot_status: cannot track_in a waiting lot')
        ),
        lotE
      )
    ).toBe(
      t('mes.err.code.lot_status_stage', {
        stage: t('mes.exec.stage.track_in'),
        status: enumLabel('lot_status', 'waiting'),
      })
    )
    expect(
      mesErrorMessage(
        axErr(422, field('lot_status', 'lot_status: lot is merged')),
        lotE
      )
    ).toBe(
      t('mes.err.code.lot_status_is', {
        status: enumLabel('lot_status', 'merged'),
      })
    )
    expect(
      mesErrorMessage(
        axErr(
          422,
          field('lot_status', 'lot_status: split qty must leave the parent')
        ),
        lotE
      )
    ).toBe(t('mes.err.code.lot_status'))
  })

  it('合批源重复或包含目标（P14）', () => {
    for (const msg of [
      'lot_status: duplicate source lots',
      'lot_status: sources include the target lot',
    ])
      expect(mesErrorMessage(axErr(422, field('lot_status', msg)), lotE)).toBe(
        t('mes.err.code.merge_source_invalid')
      )
  })

  it.each([
    [409, 'lot_busy'],
    [409, 'batch_blocked'],
    [409, 'idempotency_in_progress'],
    [422, 'idempotency_key_mismatch'],
    [422, 'idempotency_key_reused'],
    [422, 'merge_source_invalid'],
    [422, 'rework_route_missing'],
  ])('%i %s：按 detail.code 识别（N5）', (status, code) => {
    const want = t(`mes.err.code.${code}`)
    expect(mesErrorMessage(axErr(status, { code, message: 'x' }), lotE)).toBe(
      want
    )
    expect(mesErrorMessage(axErr(status, { code, items: [] }), undefined)).toBe(
      want
    )
    expect(mesCodeMessage(axErr(status, { code }))).toBe(want)
  })

  it('非错误码保持原有处理', () => {
    expect(
      mesCodeMessage(axErr(409, 'Record is referenced by other records'))
    ).toBeNull()
    const msg = mesErrorMessage(
      axErr(422, field('comment', 'comment: required')),
      lotE
    )
    expect(msg).toContain(t('mes.err.required'))
  })

  it('每个错误码在中英日都有翻译', async () => {
    const [zh, en, ja] = await Promise.all([
      import('@/i18n/locales/zh-CN.json'),
      import('@/i18n/locales/en.json'),
      import('@/i18n/locales/ja.json'),
    ])
    const keys = [
      'on_hold',
      'lot_status',
      'lot_status_is',
      'lot_status_stage',
      'lot_busy',
      'batch_blocked',
      'idempotency_in_progress',
      'idempotency_key_mismatch',
      'idempotency_key_reused',
      'merge_source_invalid',
      'rework_route_missing',
    ]
    for (const l of [zh, en, ja])
      for (const k of keys)
        expect((l.mes.err.code as Record<string, string>)[k]).toBeTruthy()
  })
})
