/** 平台控制台 · 租户成员对话框：成员列表、添加成员、修改角色、指定 owner。 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Crown, UserPlus } from 'lucide-react'
import { ALL, api, type Member, type PlatformTenant } from '@/lib/api'
import { useApiMutation } from '@/lib/api/hooks'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  ConfirmDialog,
  DataTable,
  FormDialog,
  RowActions,
  searchFilter,
  type FilterDef,
} from '@/components/crud'
import { useLocalListParams } from '@/components/crud/use-local-list-params'

/**
 * 某租户的成员管理（平台视角，所有写操作记入平台操作日志）。
 *
 * @param tenant 目标租户。
 * @param onClose 关闭回调。
 */
export function TenantMembersDialog({
  tenant,
  onClose,
}: {
  tenant: PlatformTenant
  onClose: () => void
}) {
  const tid = tenant.id
  const filters: FilterDef[] = [searchFilter(t('table.searchUsers'))]
  const lp = useLocalListParams()
  const q = useQuery({
    queryKey: ['platform', 'members', tid, lp.query],
    queryFn: () => api.platform.members(tid, lp.query),
  })
  const roles = useQuery({
    queryKey: ['platform', 'tenant-roles', tid],
    queryFn: () => api.platform.tenantRoles(tid, ALL),
  })
  const roleOptions =
    roles.data?.data.map((r) => ({ value: r.name, label: r.name })) ?? []
  const keys = [
    ['platform', 'members', tid],
    ['platform', 'tenants'],
  ]
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<Member | null>(null)
  const [removing, setRemoving] = useState<Member | null>(null)
  const [owner, setOwner] = useState('')
  const add = useApiMutation(
    (b: { email: string; roles: string[] }) => api.platform.addMember(tid, b),
    keys,
    t('members.added')
  )
  const setRoles = useApiMutation(
    (b: { user_id: string; roles: string[] }) =>
      api.platform.setMemberRoles(tid, b.user_id, b.roles),
    keys,
    t('members.rolesUpdated')
  )
  const remove = useApiMutation(
    (uid: string) => api.platform.removeMember(tid, uid),
    keys,
    t('members.removed')
  )
  const assign = useApiMutation(
    (email: string) => api.platform.assignOwner(tid, email),
    keys,
    t('platform.ownerAssigned')
  )
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>
            {t('platform.membersOf', { name: tenant.name })}
          </DialogTitle>
          <DialogDescription>{t('platform.membersDesc')}</DialogDescription>
        </DialogHeader>
        <form
          className='flex items-center gap-2'
          onSubmit={(e) => {
            e.preventDefault()
            if (owner.trim())
              assign.mutate(owner.trim(), { onSuccess: () => setOwner('') })
          }}
        >
          <Input
            type='email'
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
            placeholder={t('platform.ownerEmail')}
            className='max-w-xs'
          />
          <Button type='submit' variant='outline' disabled={!owner.trim()}>
            <Crown /> {t('platform.assignOwner')}
          </Button>
          <Button
            type='button'
            className='ms-auto'
            onClick={() => setAdding(true)}
          >
            <UserPlus /> {t('members.add')}
          </Button>
        </form>
        <DataTable
          rows={q.data?.data}
          total={q.data?.count}
          params={lp}
          filters={filters}
          loading={q.isLoading}
          rowKey={(r) => r.user_id}
          columns={[
            {
              header: t('common.email'),
              sortKey: 'email',
              cell: (r) => <span className='font-medium'>{r.email}</span>,
            },
            {
              header: t('common.name'),
              sortKey: 'full_name',
              cell: (r) => r.full_name ?? '—',
            },
            {
              header: t('common.roles'),
              cell: (r) => (
                <div className='flex flex-wrap gap-1'>
                  {r.roles.map((x) => (
                    <Badge
                      key={x}
                      variant={x === 'owner' ? 'default' : 'secondary'}
                    >
                      {x}
                    </Badge>
                  ))}
                </div>
              ),
            },
            {
              header: '',
              className: 'w-24',
              cell: (r) => (
                <RowActions
                  onEdit={() => setEditing(r)}
                  onDelete={() => setRemoving(r)}
                />
              ),
            },
          ]}
        />
        <FormDialog
          open={adding || !!editing}
          onOpenChange={(o) => {
            if (!o) {
              setAdding(false)
              setEditing(null)
            }
          }}
          title={
            editing
              ? t('members.rolesOf', { email: editing.email })
              : t('members.add')
          }
          fields={[
            {
              name: 'email',
              label: t('common.email'),
              type: 'email',
              required: true,
              hidden: !!editing,
            },
            {
              name: 'roles',
              label: t('common.roles'),
              type: 'multi',
              options: roleOptions,
            },
          ]}
          initial={{
            email: '',
            roles: editing?.roles ?? ['member'],
          }}
          onSubmit={(v) =>
            editing
              ? setRoles.mutateAsync({
                  user_id: editing.user_id,
                  roles: v.roles as string[],
                })
              : add.mutateAsync({
                  email: v.email as string,
                  roles: v.roles as string[],
                })
          }
        />
        <ConfirmDialog
          open={!!removing}
          onOpenChange={(o) => !o && setRemoving(null)}
          title={t('members.remove')}
          desc={t('members.removeDesc', {
            email: removing?.email,
            tenant: tenant.name,
          })}
          destructive
          confirmText={t('common.delete')}
          handleConfirm={() =>
            removing &&
            remove.mutate(removing.user_id, {
              onSuccess: () => setRemoving(null),
            })
          }
        />
      </DialogContent>
    </Dialog>
  )
}
