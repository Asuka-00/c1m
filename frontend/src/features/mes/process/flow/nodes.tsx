/** 路线流程图的节点：工步、子路线 / 返工路线引用、起止。 */
import { t } from '@/i18n'
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { enumLabel } from '@/features/mes/common/labels'
import { TERM_W, W, type RefData, type StepData, type TermData } from './graph'

const handle = '!size-2.5 !border-2 !border-background !bg-primary'

export function StepNode({ data, selected }: NodeProps<Node<StepData>>) {
  const s = data.step
  const sub = s.step_type === 'sub_route'
  return (
    <div
      className={cn(
        'rounded-lg border-2 bg-card px-3 py-2 text-xs shadow-sm',
        sub ? 'border-primary/60 bg-primary/5' : 'border-border',
        selected && 'ring-2 ring-primary',
        data.current &&
          'border-amber-500 bg-amber-50 ring-4 ring-amber-400/60 dark:bg-amber-950'
      )}
      style={{ width: W }}
      data-testid={`step-${String(s.seq)}`}
    >
      <Handle type='target' position={Position.Top} className={handle} />
      <div className='flex items-center gap-2'>
        <span className='rounded bg-muted px-1.5 font-mono font-semibold'>
          {String(s.seq)}
        </span>
        <span className='truncate font-medium'>
          {String((sub ? s.sub_route_label : s.operation_label) ?? '')}
        </span>
      </div>
      <div className='mt-1 flex gap-1'>
        <Badge variant='outline' className='text-[10px]'>
          {enumLabel('step_type', String(s.step_type))}
        </Badge>
        {data.current && (
          <Badge className='bg-amber-500 text-[10px] text-white'>
            {t('mes.currentStep')}
          </Badge>
        )}
        {!!s.is_optional && (
          <Badge variant='secondary' className='text-[10px]'>
            {t('mes.field.route_step.is_optional')}
          </Badge>
        )}
      </div>
      <Handle type='source' position={Position.Bottom} className={handle} />
      <Handle
        type='source'
        id='side'
        position={Position.Right}
        className={handle}
      />
      <Handle
        type='target'
        id='side-in'
        position={Position.Left}
        className={handle}
      />
    </div>
  )
}

export function RefNode({ data, selected }: NodeProps<Node<RefData>>) {
  return (
    <div
      className={cn(
        'rounded-lg border-2 border-dashed bg-card px-3 py-2 text-xs',
        data.kind === 'rework'
          ? 'border-destructive/60 bg-destructive/5'
          : 'border-primary/60 bg-primary/5',
        !data.linked && 'opacity-60',
        selected && 'ring-2 ring-primary'
      )}
      style={{ width: W }}
    >
      <Handle type='target' position={Position.Left} className={handle} />
      <div className='font-medium'>
        {data.kind === 'rework' ? t('mes.reworkRoute') : t('mes.subRoute')}:{' '}
        {data.label}
      </div>
      {data.steps && (
        <ol className='mt-1 space-y-0.5 text-muted-foreground'>
          {data.steps.map((x) => (
            <li key={x.id}>
              {String(x.seq)} ·{' '}
              {String(x.operation_label ?? x.sub_route_label ?? '')}
            </li>
          ))}
        </ol>
      )}
      <Handle type='source' position={Position.Right} className={handle} />
    </div>
  )
}

export function TermNode({ data }: NodeProps<Node<TermData>>) {
  return (
    <div
      className='rounded-full border-2 bg-muted py-1 text-center text-xs font-semibold'
      style={{ width: TERM_W }}
    >
      <Handle type='target' position={Position.Top} className={handle} />
      {data.label}
      <Handle type='source' position={Position.Bottom} className={handle} />
    </div>
  )
}
