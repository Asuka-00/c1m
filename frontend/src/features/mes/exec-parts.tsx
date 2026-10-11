import { useState } from 'react'
import { t } from '@/i18n'
import { Check, ShieldAlert, TriangleAlert, X, Zap } from 'lucide-react'
import { EXEC_STAGES, type CheckResult, type ExecStage } from '@/lib/api/mes'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { enumLabel } from './labels'

const NONE = '__none'

/** Labelled select over simple options (id/label); '' = none. */
export function Pick({
  id,
  label,
  value,
  onChange,
  options,
  required,
  none = true,
  disabled,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
  options: { id: string; label: React.ReactNode; disabled?: boolean }[]
  required?: boolean
  none?: boolean
  disabled?: boolean
}) {
  return (
    <div className='grid gap-1'>
      <Label htmlFor={id}>
        {label}
        {required && <span className='text-destructive'> *</span>}
      </Label>
      <Select
        value={value || NONE}
        onValueChange={(v) => onChange(v === NONE ? '' : v)}
        disabled={disabled}
      >
        <SelectTrigger id={id} className='w-full'>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {none && <SelectItem value={NONE}>—</SelectItem>}
          {options.map((o) => (
            <SelectItem key={o.id} value={o.id} disabled={o.disabled}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

/** Move In -> Track In -> Track Out -> Move Out with the next stage active. */
export function StageBar({
  next,
  status,
  auto,
}: {
  next: ExecStage | null
  status: string
  auto?: Record<ExecStage, boolean>
}) {
  const idx = next ? EXEC_STAGES.indexOf(next) : EXEC_STAGES.length
  return (
    <ol className='flex flex-wrap items-center gap-2' data-testid='stage-bar'>
      {EXEC_STAGES.map((s, i) => (
        <li
          key={s}
          className={cn(
            'flex items-center gap-2 rounded-full border px-3 py-1 text-sm',
            i === idx && 'border-primary bg-primary text-primary-foreground',
            i < idx && 'border-primary text-primary'
          )}
        >
          {i < idx ? (
            <Check className='size-4' />
          ) : (
            <span className='font-semibold'>{i + 1}</span>
          )}
          {t(`mes.exec.stage.${s}`)}
          {auto?.[s] && (
            <Zap className='size-3.5' aria-label={t('mes.exec.auto')} />
          )}
        </li>
      ))}
      <li className='ms-2 text-sm text-muted-foreground'>
        {enumLabel('lot_status', status)}
      </li>
    </ol>
  )
}

const RESULT_STYLE: Record<string, string> = {
  pass: 'border-emerald-500 text-emerald-700 dark:text-emerald-400',
  warn: 'border-amber-500 text-amber-700 dark:text-amber-400',
  block: 'border-destructive text-destructive',
  overridden: 'border-violet-500 text-violet-700 dark:text-violet-400',
}

export function ResultBadge({ r }: { r: string }) {
  const Icon =
    r === 'pass'
      ? Check
      : r === 'warn'
        ? TriangleAlert
        : r === 'block'
          ? X
          : ShieldAlert
  return (
    <Badge variant='outline' className={cn('gap-1', RESULT_STYLE[r])}>
      <Icon className='size-3' />
      {enumLabel('check_result', r)}
    </Badge>
  )
}

/** Check results of the last attempt / preview; override form on blocks. */
export function CheckPanel({
  results,
  blocked,
  canOverride,
  onOverride,
  busy,
}: {
  results: CheckResult[] | null
  blocked: boolean
  canOverride: boolean
  onOverride: (reason: string) => void
  busy?: boolean
}) {
  const [reason, setReason] = useState('')
  if (!results) return null
  const shown = results.filter((r) => r.applicable || r.result !== 'pass')
  const hard = results.some((r) => r.result === 'block' && !r.overridable)
  return (
    <div className='space-y-2' data-testid='check-panel'>
      {shown.length === 0 && (
        <p className='text-sm text-muted-foreground'>
          {t('mes.exec.noChecks')}
        </p>
      )}
      <ul className='divide-y rounded-md border text-sm'>
        {shown.map((r, i) => (
          <li key={i} className='flex items-start gap-2 px-3 py-2'>
            <ResultBadge r={r.result} />
            <div className='min-w-0'>
              <div className='font-medium'>
                {r.rule_code
                  ? `${r.rule_code} · ${enumLabel('check_type', r.check_type)}`
                  : enumLabel('check_type', r.check_type)}
                {r.plan_code && (
                  <span className='ms-2 text-xs text-muted-foreground'>
                    {r.plan_code}
                  </span>
                )}
              </div>
              <div className='break-words text-muted-foreground'>
                {r.message}
              </div>
            </div>
          </li>
        ))}
      </ul>
      {blocked && canOverride && !hard && (
        <div className='space-y-2 rounded-md border border-destructive/50 p-3'>
          <Label htmlFor='override-reason'>
            {t('mes.exec.overrideReason')}
            <span className='text-destructive'> *</span>
          </Label>
          <Textarea
            id='override-reason'
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
          />
          <Button
            variant='destructive'
            disabled={!reason.trim() || busy}
            onClick={() => onOverride(reason.trim())}
          >
            <ShieldAlert className='size-4' />
            {t('mes.exec.override')}
          </Button>
        </div>
      )}
      {blocked && !canOverride && (
        <p className='text-sm text-destructive'>{t('mes.exec.noOverride')}</p>
      )}
    </div>
  )
}
