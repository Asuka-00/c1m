/** 批量作业页面：同一设备上多个批次一起 Track In / Track Out。 */
import { useMemo, useState } from 'react'
import { AxiosError } from 'axios'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Play, Square } from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import { eqpApi } from '@/lib/api/mes/equipment'
import {
  execApi,
  type BatchItem,
  type BatchStage,
  type QueueRow,
} from '@/lib/api/mes/execution'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  DataTable,
  Page,
  clientList,
  useListParams,
  type FilterDef,
} from '@/components/crud'
import { MES_PERM, useMesCan } from '@/features/mes/common/mes-perm'
import { RefLink } from '@/features/mes/common/ref-link'
import { mesErrorMessage } from '@/features/mes/common/required'
import { ChamberPick } from '../shared/chamber-pick'
import { Pick } from '../shared/exec-parts'
import { BatchResult } from './batch-result'

/** 取行中某字段的去重选项。 */
function distinct(rows: QueueRow[], k: 'product' | 'operation') {
  return [...new Set(rows.map((r) => r[k]).filter(Boolean) as string[])]
    .sort()
    .map((v) => ({ value: v, label: v }))
}

/** 批量作业。 */
export default function BatchOps() {
  const tk = useTenantKey()
  const qc = useQueryClient()
  const [stage, setStage] = useState<BatchStage>('track_in')
  const [eq, setEq] = useState('')
  const [sel, setSel] = useState<string[]>([])
  const [chambers, setChambers] = useState<string[]>([])
  const [recipe, setRecipe] = useState('')
  const [items, setItems] = useState<BatchItem[] | null>(null)
  const board = useQuery({
    queryKey: ['mes', 'eqp', tk, 'board'],
    queryFn: eqpApi.board,
  })
  const cand = useQuery({
    queryKey: ['mes', 'exec', tk, 'batch', stage, eq],
    queryFn: () => execApi.batchCandidates(stage, eq),
    enabled: !!eq,
  })
  const all = useMemo(() => cand.data?.lots ?? [], [cand.data])
  const filters: FilterDef[] = [
    { type: 'text', name: 'q', placeholder: t('mes.batch.search') },
    {
      type: 'select',
      name: 'product',
      label: t('mes.batch.allProducts'),
      options: distinct(all, 'product'),
    },
    {
      type: 'select',
      name: 'operation',
      label: t('mes.batch.allOps'),
      options: distinct(all, 'operation'),
    },
  ]
  const lp = useListParams(filters)
  const view = clientList(all, lp, {
    text: (r) => `${r.code} ${r.carrier ?? ''}`,
  })
  const reset = () => {
    setSel([])
    setItems(null)
  }
  const canWrite = useMesCan()(MES_PERM.execWrite)
  const run = useMutation({
    mutationFn: () =>
      execApi.batchStage(stage, sel, {
        equipment_id: eq,
        ...(stage === 'track_in'
          ? { chamber_ids: chambers, recipe_id: recipe || null }
          : {}),
      }),
    onSuccess: (r) => {
      setItems(r)
      setSel([])
      const ok = r.filter((x) => x.ok).length
      toast.success(t('mes.batch.done', { ok, total: r.length }))
      qc.invalidateQueries({ queryKey: ['mes'] })
    },
    onError: (e) => {
      const d =
        e instanceof AxiosError
          ? (e.response?.data as { detail?: { items?: BatchItem[] } })?.detail
          : null
      if (d?.items) {
        setItems(d.items)
        toast.error(t('mes.batch.blocked'))
      } else toast.error(mesErrorMessage(e, undefined))
    },
  })
  const allSel =
    view.rows.length > 0 && view.rows.every((r) => sel.includes(r.id))
  return (
    <Page title={t('menu.mes-batch-ops')} description={t('mes.batch.hint')}>
      <Card>
        <CardContent className='grid gap-4 pt-6 sm:grid-cols-3'>
          <Tabs
            value={stage}
            onValueChange={(v) => {
              setStage(v as BatchStage)
              reset()
            }}
          >
            <TabsList>
              <TabsTrigger value='track_in'>
                {t('mes.exec.stage.track_in')}
              </TabsTrigger>
              <TabsTrigger value='track_out'>
                {t('mes.exec.stage.track_out')}
              </TabsTrigger>
            </TabsList>
          </Tabs>
          <Pick
            id='batch-eqp'
            label={t('mes.exec.equipment')}
            required
            value={eq}
            onChange={(v) => {
              setEq(v)
              setChambers([])
              setRecipe('')
              reset()
            }}
            options={(board.data ?? []).map((e) => ({
              id: e.id,
              label: `${e.code} · ${e.name}`,
            }))}
          />
          {stage === 'track_in' && (cand.data?.recipes.length ?? 0) > 0 && (
            <Pick
              id='batch-recipe'
              label={t('mes.exec.recipe')}
              value={recipe}
              onChange={setRecipe}
              options={(cand.data?.recipes ?? []).map((r) => ({
                id: r.id,
                label: `${r.code} v${r.version}`,
              }))}
            />
          )}
          {stage === 'track_in' && (
            <div className='sm:col-span-3'>
              <ChamberPick
                options={cand.data?.chambers ?? []}
                value={chambers}
                onChange={setChambers}
              />
            </div>
          )}
        </CardContent>
      </Card>
      <DataTable
        rows={view.rows}
        total={view.total}
        params={lp}
        filters={filters}
        loading={cand.isLoading && !!eq}
        rowKey={(r) => r.id}
        toolbar={
          <Button
            disabled={!canWrite || sel.length < 2 || run.isPending}
            onClick={() => run.mutate()}
            data-testid='batch-run'
          >
            {stage === 'track_in' ? (
              <Play className='size-4' />
            ) : (
              <Square className='size-4' />
            )}
            {t('mes.batch.run', {
              stage: t(`mes.exec.stage.${stage}`),
              n: sel.length,
            })}
          </Button>
        }
        columns={[
          {
            header: '',
            headerNode: (
              <Checkbox
                aria-label={t('mes.batch.selectAll')}
                checked={allSel}
                onCheckedChange={(v) =>
                  setSel(
                    v
                      ? [...new Set([...sel, ...view.rows.map((r) => r.id)])]
                      : sel.filter((x) => !view.rows.some((r) => r.id === x))
                  )
                }
              />
            ),
            cell: (r) => (
              <Checkbox
                aria-label={r.code}
                checked={sel.includes(r.id)}
                onCheckedChange={(v) =>
                  setSel(v ? [...sel, r.id] : sel.filter((x) => x !== r.id))
                }
              />
            ),
          },
          {
            header: t('mes.batch.lot'),
            sortKey: 'code',
            cell: (r) => <RefLink target='lot' id={r.id} label={r.code} />,
          },
          {
            header: t('mes.batch.product'),
            sortKey: 'product',
            cell: (r) => r.product ?? '—',
          },
          {
            header: t('mes.batch.step'),
            sortKey: 'step_seq',
            cell: (r) => `${r.step_seq ?? ''} · ${r.operation ?? ''}`,
          },
          {
            header: t('mes.batch.carrier'),
            sortKey: 'carrier',
            cell: (r) => r.carrier ?? '—',
          },
          {
            header: t('mes.batch.qty'),
            sortKey: 'qty',
            className: 'text-right tabular-nums',
            cell: (r) => r.qty,
          },
        ]}
      />
      {items && (
        <Card>
          <CardContent className='pt-6'>
            <BatchResult items={items} />
          </CardContent>
        </Card>
      )}
    </Page>
  )
}
