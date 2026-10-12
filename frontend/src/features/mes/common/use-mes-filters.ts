/** 根据实体元数据生成表格筛选定义。 */
import { useMemo } from 'react'
import { t } from '@/i18n'
import { mesApi, type MesEntity } from '@/lib/api/mes/common'
import { boolOptions, searchFilter, type FilterDef } from '@/components/crud'
import { enumLabel, fieldLabel, rowLabel, statusLabel } from './labels'

/** 各实体筛选的默认值（仍可切换为“全部”）：Hold 默认只看生效中。 */
const FILTER_DEFAULTS: Record<string, Record<string, string>> = {
  lot_hold: { is_active: 'true' },
}

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
          defaultValue: FILTER_DEFAULTS[e.code]?.[f.column],
        })
      else if (f.type === 'ref')
        defs.push({
          type: 'select',
          name: f.column,
          label: t('mes.allOf', { field: fieldLabel(e, f) }),
          optionsKey: ['mes', f.ref, 'filter-options'],
          // 远程搜索：数据量大时不受单页条数限制
          search: async (q) =>
            (
              await mesApi.list(f.ref!, { q: q || undefined, page_size: 30 })
            ).data.map((r) => ({ value: r.id, label: rowLabel(r) })),
          resolve: async (id) => rowLabel(await mesApi.get(f.ref!, id)),
        })
    }
    // 日期范围：首个列表中显示的日期 / 时间字段；日志类实体（按 created_at 排序）用创建时间
    const df = e.fields.find(
      (f) =>
        f.list &&
        (f.type === 'date' || f.type === 'datetime') &&
        !hide.includes(f.column)
    )
    if (df)
      defs.splice(1, 0, {
        type: 'daterange',
        name: df.column,
        label: fieldLabel(e, df),
        kind: df.type === 'date' ? 'date' : 'datetime',
      })
    else if (e.sort_default === 'created_at')
      defs.splice(1, 0, {
        type: 'daterange',
        name: 'created_at',
        label: t('mes.at'),
        kind: 'datetime',
      })
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
