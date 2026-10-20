import i18n from '@/i18n'
import { afterEach, describe, expect, it } from 'vitest'
import {
  checkMessage,
  codeText,
  itemText,
  noteText,
  partsText,
  systemText,
} from './backend-text'
import { ErrorCode } from './error-codes'

afterEach(() => i18n.changeLanguage('zh-CN'))

describe('检查结果说明（msg_parts）', () => {
  it('按消息键与参数翻译，状态参数嵌套翻译为枚举文案', async () => {
    await i18n.changeLanguage('zh-CN')
    expect(
      checkMessage({
        message: 'carrier C1 cleaning overdue',
        msg_parts: [
          { key: 'carrier_clean.overdue', params: { carrier: 'C1' } },
        ],
      })
    ).toBe('载具 C1 清洗已超期')
    expect(
      partsText(
        [{ key: 'wo_status.bad', params: { status: 'on_hold' } }],
        'work order is on_hold'
      )
    ).toBe('工单状态为「暂停」')
    await i18n.changeLanguage('ja')
    expect(
      partsText(
        [
          {
            key: 'split_merge_rule.src_status',
            params: { lot: 'L1', status: 'running' },
          },
        ],
        ''
      )
    ).toBe('L1：「処理中」のロットは統合できません')
  })

  it('多条说明按语言分隔符拼接', async () => {
    await i18n.changeLanguage('en')
    expect(
      partsText(
        [
          {
            key: 'material_sufficient.short',
            params: { material: 'M1', need: '5', available: '2' },
          },
          {
            key: 'material_sufficient.short',
            params: { material: 'M2', need: '1', available: '0' },
          },
        ],
        ''
      )
    ).toBe('M1: need 5, available 2; M2: need 1, available 0')
  })

  it('没有 msg_parts 或缺译文时回退后端英文', () => {
    expect(checkMessage({ message: 'legacy text' })).toBe('legacy text')
    expect(
      partsText([{ key: 'nope.missing', params: {} }], 'fallback english')
    ).toBe('fallback english')
  })
})

describe('错误码 error.code_<n>', () => {
  it('按数字错误码 + 参数翻译，非数字 / 未知码返回 null', async () => {
    await i18n.changeLanguage('zh-CN')
    expect(codeText(ErrorCode.CARRIER_BUSY, { carrier: 'C9' })).toBe(
      '载具 C9 中仍有批次'
    )
    expect(codeText(ErrorCode.LOT_TERMINAL, { status: 'merged' })).toBe(
      '批次状态为「已合批（终止）」'
    )
    expect(codeText(999999)).toBeNull()
    expect(codeText('carrier_busy')).toBeNull()
    expect(codeText(undefined)).toBeNull()
  })

  it('字段规则译文用 {{field}} 引用字段显示名', async () => {
    await i18n.changeLanguage('zh-CN')
    const x = {
      code: ErrorCode.FIELD_MIN,
      params: { min: 1 },
      loc: ['body', 'qty'],
    }
    expect(itemText(x)).toBe('qty: 不能小于 1')
    expect(itemText(x, (n) => (n === 'qty' ? '数量' : n))).toBe(
      '数量: 不能小于 1'
    )
    await i18n.changeLanguage('en')
    expect(itemText(x, () => 'Qty')).toBe('Qty: Must be at least 1')
  })

  it('独立句子没有 {{field}} 时不加字段名', async () => {
    await i18n.changeLanguage('zh-CN')
    expect(
      itemText({ code: ErrorCode.BATCH_SIZE, params: { min: 2, max: 25 } })
    ).toBe('请选择 2–25 个批次')
    expect(itemText({})).toBeNull()
  })

  it('config 项错误用 label_key 的译文当字段名', async () => {
    await i18n.changeLanguage('zh-CN')
    expect(
      itemText({
        code: ErrorCode.FIELD_REQUIRED,
        loc: ['values', 'app_name'],
        label_key: 'config.items.branding.app_name',
      })
    ).toBe('产品名称: 必填')
  })

  it('服务端参数不能覆盖语言等 i18next 选项', async () => {
    await i18n.changeLanguage('zh-CN')
    expect(codeText(ErrorCode.CARRIER_BUSY, { carrier: 'C9', lng: 'en' })).toBe(
      '载具 C9 中仍有批次'
    )
  })
})

describe('系统说明', () => {
  it('Hold / E10 履历的 note 按 key 翻译，并保留人工备注', async () => {
    await i18n.changeLanguage('zh-CN')
    expect(
      noteText({
        key: 'qtime_expired',
        params: { rule: 'QT', minutes: '35', max: 30 },
      })
    ).toBe('Q-Time QT 超时：35 > 30 分钟')
    expect(
      systemText('lot_hold', 'comment', {
        note: { key: 'inherited', params: { lot: 'L1' } },
        comment: '工程评审',
      })
    ).toBe('继承自 L1 · 工程评审')
    expect(systemText('lot_hold', 'comment', { comment: '人工' })).toBeNull()
    expect(
      systemText('check_log', 'message', {
        message: 'x',
        context: { msg_parts: [{ key: 'lot_hold.on_hold', params: {} }] },
      })
    ).toBe('批次处于 Hold')
  })
})
