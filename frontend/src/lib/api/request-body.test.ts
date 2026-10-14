import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { MesEntity } from '@/lib/api/mes/common'
import { toPayload } from '@/features/mes/common/form-payload'
import { http } from './client'
import { eqpApi, mountApi } from './mes/equipment'
import { execApi } from './mes/execution'
import { BODY_KEYS } from './request-body'

const post = vi.spyOn(http, 'post')
const sent = () =>
  post.mock.calls[post.mock.calls.length - 1][1] as Record<string, unknown>
const keys = (o: unknown) => Object.keys(o as object).sort()
const junk = { id: 'x', lot_code: 'L1', created_at: 't', _label: 'y' }

beforeEach(() => {
  post.mockReset()
  post.mockResolvedValue({ data: {} })
})

describe('extra=forbid 请求体白名单', () => {
  it('track-in / preview：只发 StageIn 字段，子项也裁剪', async () => {
    const body = {
      ...junk,
      equipment_id: 'e',
      override: true,
      override_reason: 'r',
      dc: [{ measurement_item_id: 'm', value: 1, item_name: 'x' }],
      scrap: [{ reason_id: 'r', qty: 1, reason_code: 'c' }],
    }
    await execApi.stage('L', 'track-in' as never, body as never)
    expect(keys(sent())).toEqual(
      ['dc', 'equipment_id', 'override', 'override_reason', 'scrap'].sort()
    )
    expect(keys((sent().dc as unknown[])[0])).toEqual([
      'measurement_item_id',
      'value',
    ])
    expect(keys((sent().scrap as unknown[])[0])).toEqual(['qty', 'reason_id'])
    await execApi.preview('L', 'track-out' as never, body as never)
    expect(
      keys(sent()).every((k) =>
        (BODY_KEYS.stage as readonly string[]).includes(k)
      )
    ).toBe(true)
  })

  it('batch：lot_ids + StageIn', async () => {
    await execApi.batchStage('track-in' as never, ['a'], {
      ...junk,
      equipment_id: 'e',
    } as never)
    expect(keys(sent())).toEqual(['equipment_id', 'lot_ids'])
  })

  it('split / merge：spread 的表单不再带出多余字段', async () => {
    await execApi.split(
      'L',
      [{ unit_ids: ['u'], qty: 1, key: 'k' }] as never,
      {
        ...junk,
        comment: 'c',
      } as never
    )
    expect(keys(sent())).toEqual(['children', 'comment'])
    expect(keys((sent().children as unknown[])[0])).toEqual(['qty', 'unit_ids'])
    await execApi.merge('L', ['b'], { ...junk, preview: true } as never)
    expect(keys(sent())).toEqual(['preview', 'source_lot_ids'])
  })

  it('transform：outputs / sources / manual_good 逐层裁剪', async () => {
    await execApi.transform({
      ...junk,
      transform_type: 'die_bank',
      input_lot_ids: ['a'],
      outputs: [
        {
          product_id: 'p',
          qty: 1,
          product_name: 'n',
          sources: [{ wafer_id: 'w', qty: 1, slot: 3 }],
        },
      ],
      manual_good: [
        { wafer_id: 'w', good_qty: 1, fail_qty: 0, wafer_code: 'W' },
      ],
    } as never)
    const out = (sent().outputs as Record<string, unknown>[])[0]
    expect(keys(sent())).toEqual([
      'input_lot_ids',
      'manual_good',
      'outputs',
      'transform_type',
    ])
    expect(keys(out)).toEqual(['product_id', 'qty', 'sources'])
    expect(keys((out.sources as unknown[])[0])).toEqual(['qty', 'wafer_id'])
    expect(keys((sent().manual_good as unknown[])[0])).toEqual([
      'fail_qty',
      'good_qty',
      'wafer_id',
    ])
  })

  it('E10 / 告警清除 / mount', async () => {
    await eqpApi.changeE10('E', {
      ...junk,
      to_state_id: 's',
      comment: 'c',
    } as never)
    expect(keys(sent())).toEqual(['comment', 'to_state_id'])
    await eqpApi.alarmClear('A', { ...junk, comment: 'c' } as never)
    expect(keys(sent())).toEqual(['comment'])
    await mountApi.mount('E', {
      ...junk,
      port_code: 'P1',
      material_lot_id: 'm',
    } as never)
    expect(keys(sent())).toEqual(['material_lot_id', 'port_code'])
  })
})

describe('通用实体表单提交体', () => {
  const entity = {
    code: 'product',
    fields: [
      { name: 'code', column: 'code', type: 'str' },
      { name: 'family', column: 'family_id', type: 'ref' },
      { name: 'qty', column: 'qty', type: 'int' },
      {
        name: 'created_at',
        column: 'created_at',
        type: 'datetime',
        system: true,
      },
    ],
  } as unknown as MesEntity
  it('只发 _meta 可写字段 + attrs，不带 id / 时间戳 / 显示字段', () => {
    const v = {
      id: 'x',
      code: 'P',
      family_id: 'f',
      family: 'Fam',
      family_code: 'F',
      _label: 'l',
      qty: '2',
      created_at: 't',
      updated_at: 't',
      attrs: {},
    }
    expect(keys(toPayload(entity, v, new Set()))).toEqual([
      'attrs',
      'code',
      'family_id',
      'qty',
    ])
  })
})
