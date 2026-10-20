import { en, ja, zh } from '@/test-utils/locales'
import { describe, expect, it } from 'vitest'

/** 合并菜单 → 首个页签（与 backend/app/platform/menus/layout.py 的 MERGED 一致）。 */
const MERGED_FIRST_TAB: Record<string, string> = {
  'mes-check-config': 'mes-check_rule',
  'mes-product-master': 'mes-product',
  'mes-material-master': 'mes-material',
  'mes-carrier-master': 'mes-carrier',
  'mes-equipment-master': 'mes-equipment',
  'mes-e10-model': 'mes-e10_state',
  'mes-lot-rules': 'mes-lot_type',
  'mes-factory-model': 'mes-site',
  'mes-calendar': 'mes-work_calendar',
  'mes-route-master': 'mes-route',
  'mes-recipe-param': 'mes-recipe',
  'mes-dc-config': 'mes-dc_plan',
  'mes-lot-history': 'mes-lot-trace',
  'mes-warehouse-master': 'mes-warehouse',
}

const menu = {
  en: en.menu as Record<string, string>,
  zh: zh.menu as Record<string, string>,
  ja: ja.menu as Record<string, string>,
}

describe('菜单标题（方案 A）', () => {
  it('分组与改名后的标题', () => {
    expect(menu.zh['g-execution']).toBe('批次作业')
    expect(menu.zh['g-equipment']).toBe('机台管理')
    expect(menu.zh['g-exception']).toBe('异常处置')
    expect(menu.zh['g-wip']).toBe('在制与查询')
    expect(menu.zh['mes-lot-start']).toBe('投片/开批')
    expect(menu.zh['mes-carrier-ops']).toBe('载具作业')
    expect(menu.zh['mes-tool']).toBe('耗材/治具寿命')
    expect(menu.en['mes-check_log']).toBe('Interlock Log')
    expect(menu.en['mes-change_order']).toBe('ECN')
    expect(menu.zh['mes-e10_state']).toBe('E10 状态模型')
  })

  it('日文 Q-Time 带空格，中文 Hold 不叫冻结', () => {
    const jaVals = Object.values(menu.ja)
    expect(menu.ja['mes-qtime-monitor']).toBe('Q-Time 監視')
    expect(menu.ja['mes-qtime_rule']).toBe('Q-Time ルール')
    expect(jaVals.some((v) => v.includes('Q タイム'))).toBe(false)
    expect(jaVals.some((v) => /Q-Time(?! )/.test(v))).toBe(false)
    expect(Object.values(menu.zh).some((v) => v.includes('冻结'))).toBe(false)
  })

  it('合并菜单与首个页签不重名', () => {
    expect({
      'mes-warehouse-master': menu.zh['mes-warehouse-master'],
      'mes-equipment-master': menu.zh['mes-equipment-master'],
      'mes-product-master': menu.zh['mes-product-master'],
      'mes-material-master': menu.zh['mes-material-master'],
      'mes-carrier-master': menu.zh['mes-carrier-master'],
      'mes-e10-model': menu.zh['mes-e10-model'],
      'mes-route-master': menu.zh['mes-route-master'],
      'mes-calendar': menu.zh['mes-calendar'],
    }).toEqual({
      'mes-warehouse-master': '仓库主数据',
      'mes-equipment-master': '机台主数据',
      'mes-product-master': '产品主数据',
      'mes-material-master': '物料主数据',
      'mes-carrier-master': '载具主数据',
      'mes-e10-model': 'E10 状态配置',
      'mes-route-master': '工艺流程配置',
      'mes-calendar': '日历与班次',
    })
    for (const [key, tab] of Object.entries(MERGED_FIRST_TAB))
      for (const m of Object.values(menu)) expect(m[key], key).not.toBe(m[tab])
  })
})
