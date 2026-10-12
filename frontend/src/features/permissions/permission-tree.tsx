import { useState } from 'react'
import { t } from '@/i18n'
import { ChevronDown, ChevronRight, Folder } from 'lucide-react'
import type { Permission } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { groupPermissions } from './permission-groups'

/** Checkbox tree: resource nodes (tri-state) with permission leaves. */
export function PermissionTree({
  perms,
  value,
  onChange,
  disabled,
}: {
  perms: Permission[]
  value: Set<string>
  onChange: (next: Set<string>) => void
  disabled?: boolean
}) {
  const groups = groupPermissions(perms)
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const toggle = (codes: string[], on: boolean) => {
    const next = new Set(value)
    codes.forEach((c) => (on ? next.add(c) : next.delete(c)))
    onChange(next)
  }
  return (
    <div className='rounded-md border' role='tree'>
      {groups.map((g) => {
        const codes = g.perms.map((p) => p.code)
        const n = codes.filter((c) => value.has(c)).length
        const state =
          n === 0 ? false : n === codes.length ? true : 'indeterminate'
        const open = !collapsed.has(g.resource)
        return (
          <div
            key={g.resource}
            role='treeitem'
            aria-expanded={open}
            className='border-b last:border-b-0'
          >
            <div className='flex items-center gap-2 bg-muted/40 px-3 py-2'>
              <button
                type='button'
                className='text-muted-foreground'
                aria-label={open ? t('common.collapse') : t('common.expand')}
                onClick={() => {
                  const s = new Set(collapsed)
                  if (open) s.add(g.resource)
                  else s.delete(g.resource)
                  setCollapsed(s)
                }}
              >
                {open ? (
                  <ChevronDown className='size-4' />
                ) : (
                  <ChevronRight className='size-4' />
                )}
              </button>
              <Checkbox
                checked={state}
                disabled={disabled}
                onCheckedChange={(c) => toggle(codes, c === true)}
                aria-label={t('permissions.allOf', { resource: g.resource })}
              />
              <Folder className='size-4 text-muted-foreground' />
              <span className='font-medium'>{g.resource}</span>
              <span className='text-xs text-muted-foreground'>
                {n}/{codes.length}
              </span>
            </div>
            {open && (
              <div
                role='group'
                className='grid gap-1 py-1 ps-14 pe-3 sm:grid-cols-2'
              >
                {g.perms.map((p) => (
                  <label
                    key={p.id}
                    className='flex items-start gap-2 rounded px-2 py-1.5 text-sm hover:bg-muted/50'
                  >
                    <Checkbox
                      className='mt-0.5'
                      checked={value.has(p.code)}
                      disabled={disabled}
                      onCheckedChange={(c) => toggle([p.code], c === true)}
                    />
                    <span className='grid min-w-0'>
                      <span className='font-mono text-xs'>
                        {p.code}{' '}
                        <Badge
                          variant='outline'
                          className='ms-1 px-1 py-0 text-[10px]'
                        >
                          {t(`permissions.scopes.${p.scope}`, {
                            defaultValue: p.scope,
                          })}
                        </Badge>
                      </span>
                      <span
                        className='truncate text-xs text-muted-foreground'
                        title={p.description ?? undefined}
                      >
                        {p.description}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
