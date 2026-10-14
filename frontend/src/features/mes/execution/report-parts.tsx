/** 报表页公共组件：KPI 卡片、简单数据表、日期区间。 */
import { useState } from 'react'
import { t } from '@/i18n'
import { Download } from 'lucide-react'
import { errorMessage } from '@/lib/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { downloadCsv } from '@/components/crud'
import { rangeInverted } from '@/components/crud/filter-defs'
import { isoDay } from './report-utils'

/** KPI 卡片。 */
export function Kpi({
  label,
  value,
}: {
  label: string
  value: React.ReactNode
}) {
  return (
    <Card className='gap-1 py-4'>
      <CardContent>
        <div className='text-sm text-muted-foreground'>{label}</div>
        <div className='text-2xl font-semibold tabular-nums'>{value}</div>
      </CardContent>
    </Card>
  )
}

/** 列定义：表头、取值、是否右对齐。 */
export interface Col<T> {
  head: string
  get: (r: T) => React.ReactNode
  right?: boolean
  /** 导出用的纯文本值（缺省时取 get 的字符串 / 数字结果） */
  text?: (r: T) => unknown
}

/** 列值的导出文本。 */
function plain<T>(c: Col<T>, r: T): unknown {
  if (c.text) return c.text(r)
  const v = c.get(r)
  return typeof v === 'string' || typeof v === 'number' ? v : ''
}

/** 带标题卡片的简单数据表（最多显示 ``max`` 行）。 */
export function DataCard<T>({
  title,
  rows,
  cols,
  max = 20,
  exportName,
}: {
  title: string
  rows: T[]
  cols: Col<T>[]
  max?: number
  /** 设置后显示“导出”按钮（CSV，导出全部行） */
  exportName?: string
}) {
  return (
    <Card className='gap-3'>
      <CardHeader className='flex flex-row items-center justify-between'>
        <CardTitle className='text-base'>{title}</CardTitle>
        {exportName && (
          <Button
            size='sm'
            variant='outline'
            disabled={!rows.length}
            onClick={() =>
              downloadCsv(
                exportName,
                cols.map((c) => c.head),
                rows.map((r) => cols.map((c) => plain(c, r)))
              )
            }
          >
            <Download className='size-4' />
            {t('mes.export')}
          </Button>
        )}
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              {cols.map((c) => (
                <TableHead key={c.head} className={c.right ? 'text-right' : ''}>
                  {c.head}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={cols.length}
                  className='text-center text-muted-foreground'
                >
                  {t('common.noResults')}
                </TableCell>
              </TableRow>
            )}
            {rows.slice(0, max).map((r, i) => (
              <TableRow key={i}>
                {cols.map((c) => (
                  <TableCell
                    key={c.head}
                    className={c.right ? 'text-right tabular-nums' : ''}
                  >
                    {c.get(r)}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

/** 日期区间输入。 */
export function DateRange({
  from,
  to,
  setFrom,
  setTo,
  error,
}: {
  from: string
  to: string
  setFrom: (v: string) => void
  setTo: (v: string) => void
  /** 报表查询错误（D77 补充二：422 range_inverted / pattern 等），显示后端文案 */
  error?: unknown
}) {
  // D77 补充一：from 晚于 to 时拦住（不写入），并提示
  const [inverted, setInverted] = useState(false)
  const pickFrom = (v: string) => {
    const bad = rangeInverted(v, to)
    setInverted(bad)
    if (!bad) setFrom(v)
  }
  const pickTo = (v: string) => {
    const bad = rangeInverted(from, v)
    setInverted(bad)
    if (!bad) setTo(v)
  }
  const today = isoDay()
  const presets: [string, string, string][] = [
    [t('table.range.today'), today, today],
    [t('table.range.last7'), isoDay(-6), today],
    [t('table.range.last30'), isoDay(-29), today],
    [t('table.range.thisMonth'), `${today.slice(0, 8)}01`, today],
  ]
  return (
    <div className='flex flex-wrap items-end gap-3'>
      <div className='flex gap-1'>
        {presets.map(([l, a, b]) => (
          <Button
            key={l}
            size='sm'
            variant={from === a && to === b ? 'secondary' : 'ghost'}
            onClick={() => {
              setInverted(false)
              setFrom(a)
              setTo(b)
            }}
          >
            {l}
          </Button>
        ))}
      </div>
      <div className='grid gap-1'>
        <Label htmlFor='rp-from'>{t('mes.report.from')}</Label>
        <Input
          id='rp-from'
          type='date'
          value={from}
          max={to || undefined}
          onChange={(e) => pickFrom(e.target.value)}
        />
      </div>
      <div className='grid gap-1'>
        <Label htmlFor='rp-to'>{t('mes.report.to')}</Label>
        <Input
          id='rp-to'
          type='date'
          value={to}
          min={from || undefined}
          onChange={(e) => pickTo(e.target.value)}
        />
      </div>
      {inverted && (
        <p className='text-sm text-destructive' data-testid='range-inverted'>
          {t('errors.rangeInverted')}
        </p>
      )}
      {!inverted && error != null && (
        <p className='text-sm text-destructive' data-testid='report-error'>
          {errorMessage(error)}
        </p>
      )}
    </div>
  )
}
