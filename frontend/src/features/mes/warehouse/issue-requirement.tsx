/** 领料单详情面板：所属工单的物料需求与已领数量。 */
import { useQuery } from '@tanstack/react-query'
import { fmtNumber, t } from '@/i18n'
import { errorMessage } from '@/lib/api/client'
import { type MesRow } from '@/lib/api/mes/common'
import { issueApi } from '@/lib/api/mes/warehouse'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

/** 工单物料需求（需求来自下达时锁定的 BOM）；缺料高亮。 */
export function IssueRequirement({ row }: { row: MesRow }) {
  const { data, error } = useQuery({
    queryKey: ['mes', 'material-issue', 'requirements', row.work_order_id],
    queryFn: () => issueApi.requirements(String(row.work_order_id)),
    retry: false,
  })
  if (error) return <p className='pt-2 text-sm'>{errorMessage(error)}</p>
  if (!data) return null
  if (!data.bom)
    return <p className='pt-2 text-sm'>{t('mes.issue.req.empty')}</p>
  return (
    <div className='space-y-2 pt-2'>
      <p className='text-sm text-muted-foreground'>
        {t('mes.issue.req.bom', { bom: data.bom })}
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t('mes.issue.req.material')}</TableHead>
            <TableHead className='text-end'>
              {t('mes.issue.req.required')}
            </TableHead>
            <TableHead className='text-end'>
              {t('mes.issue.req.issued')}
            </TableHead>
            <TableHead className='text-end'>
              {t('mes.issue.req.short')}
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.lines.map((l) => (
            <TableRow key={l.material_id}>
              <TableCell>{l.material}</TableCell>
              <TableCell className='text-end'>
                {fmtNumber(l.required)} {l.uom}
              </TableCell>
              <TableCell className='text-end'>
                {fmtNumber(l.issued)} {l.uom}
              </TableCell>
              <TableCell
                className={`text-end ${l.short > 0 ? 'font-semibold text-destructive' : ''}`}
              >
                {fmtNumber(l.short)} {l.uom}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
