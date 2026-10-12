/** 根据实体元数据生成表格筛选定义。 */
import { useMemo } from 'react'
import { t } from '@/i18n'
import { mesApi, type MesEntity } from '@/lib/api/mes/common'
import { boolOptions, searchFilter, type FilterDef } from '@/components/crud'
import { enumLabel, fieldLabel, rowLabel, statusLabel } from './labels'

/**
 * 由实体元数据生成表格筛选：关键字搜索 + 可筛选字段（枚举 / 布尔 / 引用）。
 *
 * @param e - 实体元数据
 * @param hide - 不显示的筛选字段（如已固定的父级字段）
 */
export function useMesFilters(e: MesEntity | undefined, hide: string[] = []) {
  return useMemo<FilterDef[]>(() => {
    if (!e) return [searchFilter()]
    const defs: FilterDef[] = [searchFilter()]
    for (const f of e.fields) {
      if (!f.filter || hide.includes(f.column)) continue
      if (f.type === 'enum')
        defs.push({
          type: 'select',
          name: f.column,
          label: t('mes.allOf', { field: fieldLabel(e, f) }),
          optionsKey: ['mes', 'enum-options', f.enum],
          loadOptions: async () =>
            (await mesApi.meta()).enums[f.enum!].map((v) => ({
              value: v,
              label: enumLabel(f.enum!, v),
            })),
        })
      else if (f.type === 'bool')
        defs.push({
          type: 'select',
          name: f.column,
          label: t('mes.allOf', { field: fieldLabel(e, f) }),
          options: boolOptions(t('common.yes'), t('common.no')),
        })
      else if (f.type === 'ref')
        defs.push({
          type: 'select',
          name: f.column,
          label: t('mes.allOf', { field: fieldLabel(e, f) }),
          optionsKey: ['mes', f.ref, 'filter-options'],
          loadOptions: async () =>
            (await mesApi.list(f.ref!, { page_size: 100 })).data.map((r) => ({
              value: r.id,
              label: rowLabel(r),
            })),
        })
    }
    if (e.versioned)
      defs.push({
        type: 'select',
        name: 'status',
        label: t('mes.allOf', { field: t('common.status') }),
        options: ['draft', 'active', 'inactive'].map((s) => ({
          value: s,
          label: statusLabel(s),
        })),
      })
    return defs
    // hide 在每个调用处都是稳定的字面量
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [e])
}
