import { AxiosError, AxiosHeaders } from 'axios'
import { t } from '@/i18n'
import { en, ja, zh } from '@/test-utils/locales'
import { describe, expect, it } from 'vitest'
import type { MesEntity } from '@/lib/api/mes/common'
import { detailParams } from '@/lib/backend-text'
import { ErrorCode } from '@/lib/error-codes'
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
const item = (
  f: string,
  code: number,
  params: Record<string, unknown> = {}
) => ({
  loc: ['body', f],
  msg: `${f}: english fallback`,
  type: 'value_error',
  code,
  params,
})
const lotE = { code: 'lot', fields: [] } as unknown as MesEntity
const text = (code: number, params?: Record<string, unknown>) =>
  t(`error.code_${code}`, params)

describe('mesErrorMessage：错误码对象 {code, message, params}', () => {
  it('ON_HOLD 按错误码识别', () => {
    const e = axErr(422, {
      code: ErrorCode.ON_HOLD,
      message: 'lot is on hold',
      action: 'move_out',
    })
    expect(mesErrorMessage(e, lotE)).toBe(text(ErrorCode.ON_HOLD))
    expect(mesErrorMessage(e, undefined)).toBe(text(ErrorCode.ON_HOLD))
  })

  it('LOT_STATUS 用 action 与状态生成具体提示', () => {
    expect(
      mesErrorMessage(
        axErr(422, {
          code: ErrorCode.LOT_STATUS,
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
          code: ErrorCode.LOT_STATUS,
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
    expect(
      mesErrorMessage(axErr(422, { code: ErrorCode.LOT_STATUS }), lotE)
    ).toBe(t('mes.err.code.lot_status'))
  })

  it('合批源错误按错误码识别，即使 message 不含关键词', () => {
    expect(
      mesErrorMessage(
        axErr(422, {
          code: ErrorCode.MERGE_SOURCE_INVALID,
          message: 'bad sources',
          duplicates: ['L2'],
          includes_target: false,
        }),
        lotE
      )
    ).toBe(text(ErrorCode.MERGE_SOURCE_INVALID))
  })

  it('Q-Time 规则被 Hold 引用：显示规则编码与条数，提示改为停用', () => {
    const msg = mesErrorMessage(
      axErr(409, {
        code: ErrorCode.QTIME_RULE_IN_USE,
        message: 'in use',
        qtime_rule_id: 'R-1',
        qtime_rule_code: 'QT-ETCH',
        hold_count: 3,
      }),
      { code: 'qtime_rule', fields: [] } as unknown as MesEntity
    )
    expect(msg).toBe(
      text(ErrorCode.QTIME_RULE_IN_USE, {
        qtime_rule_code: 'QT-ETCH',
        hold_count: 3,
      })
    )
    expect(msg).toContain('QT-ETCH')
    expect(msg).toContain('3')
  })

  it.each([
    [409, ErrorCode.LOT_BUSY],
    [409, ErrorCode.BATCH_BLOCKED],
    [422, ErrorCode.REWORK_ROUTE_MISSING],
    [404, ErrorCode.HOLD_NOT_FOUND],
    [422, ErrorCode.QTIME_ACTION_INVALID],
  ])('%i %i：按 detail.code 识别', (status, code) => {
    const want = text(code)
    expect(want).not.toBe(`error.code_${code}`)
    expect(mesErrorMessage(axErr(status, { code, message: 'x' }), lotE)).toBe(
      want
    )
    expect(mesCodeMessage(axErr(status, { code }))).toBe(want)
  })

  it('裸字符串 / 非数字 code 不当作错误码', () => {
    expect(mesCodeMessage(axErr(409, 'Record is referenced'))).toBeNull()
    expect(mesCodeMessage(axErr(409, { code: 'lot_busy' }))).toBeNull()
  })
})

describe('mesErrorMessage：422 字段错误项（code + params）', () => {
  it('字段规则：{{field}} 用实体字段标签，参数插值', () => {
    const e = {
      code: 'work_order',
      fields: [{ name: 'planned_qty' }],
    } as unknown as MesEntity
    const msg = mesErrorMessage(
      axErr(422, [item('planned_qty', ErrorCode.FIELD_MIN, { min: 1 })]),
      e
    )
    expect(msg).toContain('1')
    expect(msg).not.toContain('{{')
    expect(msg).toBe(
      text(ErrorCode.FIELD_MIN, {
        min: 1,
        field: t('mes.field.work_order.planned_qty'),
      })
    )
  })

  it('独立句子：参数插值，嵌套的枚举译文生效', () => {
    const msg = mesErrorMessage(
      axErr(422, [item('lot', ErrorCode.LOT_TERMINAL, { status: 'merged' })]),
      lotE
    )
    expect(msg).toContain(enumLabel('lot_status', 'merged'))
  })

  it('带行号时前缀“第 N 行”', () => {
    const msg = mesErrorMessage(
      axErr(422, [
        item('lines.1.lot', ErrorCode.RECEIPT_LOT_ON_HOLD, {
          lot: 'L1',
          line: 2,
        }),
      ]),
      lotE
    )
    expect(msg).toBe(
      t('mes.err.withLine', {
        line: 2,
        text: text(ErrorCode.RECEIPT_LOT_ON_HOLD, { lot: 'L1' }),
      })
    )
  })

  it('没有错误码的项回退英文并加校验失败前缀', () => {
    const msg = mesErrorMessage(
      axErr(422, [{ loc: ['body', 'comment'], msg: 'comment: required' }]),
      lotE
    )
    expect(msg).toContain(t('error.validation'))
    expect(msg).toContain('comment')
  })
})

describe('错误码文案齐全', () => {
  it('每个后端错误码在中英日都有翻译', () => {
    for (const l of [zh, en, ja])
      for (const code of Object.values(ErrorCode))
        expect(l.error[`code_${code}`], `code_${code}`).toBeTruthy()
  })
})

describe('错误详情插值参数', () => {
  it('取 params 与顶层标量字段，忽略 code / message / 结果列表', () => {
    expect(
      detailParams({
        code: 1,
        message: 'x',
        results: [],
        lot_code: 'L1',
        hold_count: 3,
        nested: { a: 1 },
        params: { extra: 'y' },
      })
    ).toEqual({ lot_code: 'L1', hold_count: 3, extra: 'y' })
  })

  it('i18next 选项键（如 lng / defaultValue）不会被服务端参数覆盖', () => {
    expect(
      detailParams({ lng: 'ja', defaultValue: 'x', params: { context: 'c' } })
    ).toEqual({})
    expect(
      mesCodeMessage(
        axErr(409, {
          code: ErrorCode.QTIME_RULE_IN_USE,
          qtime_rule_code: 'QT-ETCH',
          hold_count: 3,
          lng: 'ja',
        })
      )
    ).toBe(
      text(ErrorCode.QTIME_RULE_IN_USE, {
        qtime_rule_code: 'QT-ETCH',
        hold_count: 3,
      })
    )
  })
})
