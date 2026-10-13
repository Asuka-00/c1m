/** 平台用户对话框中的“所属租户”编辑器：多行（租户 + 租户角色）。 */
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Plus, Trash2 } from 'lucide-react'
import { ALL, api, type UserTenantRoles } from '@/lib/api'
import { roleLabel } from '@/lib/rbac-labels'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { TagSelect } from '@/components/crud/tag-select'
import { encodeRows } from './tenant-rows'

/** 单行：租户下拉 + 该租户角色标签多选。 */
function Row({
  row,
  tenants,
  taken,
  onChange,
  onRemove,
}: {
  row: UserTenantRoles
  tenants: { value: string; label: string }[]
  taken: string[]
  onChange: (r: UserTenantRoles) => void
  onRemove: () => void
}) {
  const roles = useQuery({
    queryKey: ['platform-tenant-roles', row.tenant_id],
    queryFn: () => api.platform.tenantRoles(row.tenant_id, ALL),
    enabled: !!row.tenant_id,
  })
  const options =
    roles.data?.data.map((r) => ({ value: r.name, label: roleLabel(r) })) ?? []
  return (
    <div className='flex items-start gap-2' data-testid='tenant-row'>
      <Select
        value={row.tenant_id || undefined}
        onValueChange={(v) => onChange({ tenant_id: v, roles: ['member'] })}
      >
        <SelectTrigger className='w-44 shrink-0' aria-label={t('users.tenant')}>
          <SelectValue placeholder={t('users.pickTenant')} />
        </SelectTrigger>
        <SelectContent>
          {tenants
            .filter(
              (o) => o.value === row.tenant_id || !taken.includes(o.value)
            )
            .map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
        </SelectContent>
      </Select>
      <div className='min-w-0 flex-1'>
        <TagSelect
          options={options}
          value={row.roles}
          onChange={(roles) => onChange({ ...row, roles })}
          placeholder={t('rbac.pickRoles')}
        />
      </div>
      <Button
        type='button'
        size='icon'
        variant='ghost'
        aria-label={t('users.removeTenant')}
        onClick={onRemove}
      >
        <Trash2 className='size-4' />
      </Button>
    </div>
  )
}

/** 所属租户编辑器：增删行，每行选择租户与租户角色。 */
export function TenantRolesEditor({
  value,
  onChange,
}: {
  value: string[]
  onChange: (v: string[]) => void
}) {
  const tenants = useQuery({
    queryKey: ['platform-tenants', 'options'],
    queryFn: () => api.platform.tenants(ALL),
  })
  const options =
    tenants.data?.data.map((x) => ({ value: x.id, label: x.name })) ?? []
  const rows = value.map((x) => JSON.parse(x) as UserTenantRoles)
  const set = (next: UserTenantRoles[]) => onChange(encodeRows(next))
  return (
    <div className='space-y-2'>
      {rows.map((r, i) => (
        <Row
          key={i}
          row={r}
          tenants={options}
          taken={rows.map((x) => x.tenant_id)}
          onChange={(n) => set(rows.map((x, j) => (j === i ? n : x)))}
          onRemove={() => set(rows.filter((_, j) => j !== i))}
        />
      ))}
      <Button
        type='button'
        variant='outline'
        size='sm'
        onClick={() => set([...rows, { tenant_id: '', roles: ['member'] }])}
      >
        <Plus className='size-4' /> {t('users.addTenant')}
      </Button>
    </div>
  )
}
