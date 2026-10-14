/** P3-F2：人员资质详情的「履历」页签（D74；样式同光罩履历）。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { errorMessage } from '@/lib/api/client'
import type { MesRow } from '@/lib/api/mes/common'
import {
  QUAL_HISTORY_LIMIT_DEFAULT,
  qualHistoryApi,
} from '@/lib/api/mes/qual-history'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { dash, qualChanges } from './qual-history-format'

const COLS = [
  'at',
  'action',
  'changes',
  'reasonId',
  'comment',
  'approvedBy',
  'username',
] as const

export function QualHistoryTab({ row }: { row: MesRow }) {
  const [limit, setLimit] = useState(QUAL_HISTORY_LIMIT_DEFAULT)
  const q = useQuery({
    queryKey: ['mes', 'operator-qual', 'history', row.id, limit],
    queryFn: () => qualHistoryApi.history(String(row.id), { limit }),
  })
  const rows = q.data?.rows ?? []
  if (q.error)
    return (
      <p className='text-sm text-destructive' data-testid='qual-history-error'>
        {errorMessage(q.error)}
      </p>
    )
  return (
    <div className='grid gap-2'>
      <Table data-testid='qual-history'>
        <TableHeader>
          <TableRow>
            {COLS.map((c) => (
              <TableHead key={c}>{t(`mes.qualHistory.col.${c}`)}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.length === 0 ? (
            <TableRow>
              <TableCell
                colSpan={COLS.length}
                className='text-muted-foreground'
              >
                {q.isLoading
                  ? t('mes.qualHistory.loading')
                  : t('mes.qualHistory.empty')}
              </TableCell>
            </TableRow>
          ) : (
            rows.map((r) => (
              <TableRow key={r.id} data-testid={`qual-log-${r.action}`}>
                <TableCell>{fmtDateTime(r.at)}</TableCell>
                <TableCell>{t(`mes.qualHistory.action.${r.action}`)}</TableCell>
                <TableCell className='max-w-80 whitespace-normal'>
                  {qualChanges(r) || '—'}
                </TableCell>
                <TableCell>{dash(r.reason_id)}</TableCell>
                <TableCell className='max-w-60 whitespace-normal'>
                  {dash(r.comment)}
                </TableCell>
                <TableCell>{dash(r.approved_by)}</TableCell>
                <TableCell>
                  {r.username === 'system'
                    ? t('mes.qualHistory.system')
                    : r.username}
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
      {rows.length >= limit && limit < 200 && (
        <Button
          size='sm'
          variant='outline'
          className='justify-self-start'
          data-testid='qual-history-more'
          onClick={() => setLimit(200)}
        >
          {t('mes.qualHistory.more')}
        </Button>
      )}
    </div>
  )
}
