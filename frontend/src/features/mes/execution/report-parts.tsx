/** 报表页公共组件：KPI 卡片、简单数据表、日期区间。 */
import { t } from '@/i18n'
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
}

/** 带标题卡片的简单数据表（最多显示 ``max`` 行）。 */
export function DataCard<T>({
  title,
  rows,
  cols,
  max = 20,
}: {
  title: string
  rows: T[]
  cols: Col<T>[]
  max?: number
}) {
  return (
    <Card className='gap-3'>
      <CardHeader>
        <CardTitle className='text-base'>{title}</CardTitle>
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
}: {
  from: string
  to: string
  setFrom: (v: string) => void
  setTo: (v: string) => void
}) {
  return (
    <div className='flex items-end gap-3'>
      <div className='grid gap-1'>
        <Label htmlFor='rp-from'>{t('mes.report.from')}</Label>
        <Input
          id='rp-from'
          type='date'
          value={from}
          onChange={(e) => setFrom(e.target.value)}
        />
      </div>
      <div className='grid gap-1'>
        <Label htmlFor='rp-to'>{t('mes.report.to')}</Label>
        <Input
          id='rp-to'
          type='date'
          value={to}
          onChange={(e) => setTo(e.target.value)}
        />
      </div>
    </div>
  )
}
