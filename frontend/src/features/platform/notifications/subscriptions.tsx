/** 通知订阅配置页面：事件类型 → 角色 / 用户，渠道与启用开关。 */
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Plus } from 'lucide-react'
import { ALL, api, type Subscription, type SubscriptionIn } from '@/lib/api'
import { useApiMutation, useCan, useCurrentTenant } from '@/lib/api/hooks'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  boolOptions,
  ConfirmDialog,
  DataTable,
  FormDialog,
  Page,
  RowActions,
  searchFilter,
  useCrudState,
  useListParams,
  type FilterDef,
  type Values,
} from '@/components/crud'
import { eventLabel } from '@/components/notify/utils'

/** 通知订阅：列表 + 新建 / 编辑 / 删除（需 notify:config 权限）。 */
export default function SubscriptionsPage() {
  const tid = useCurrentTenant()?.tenant.id ?? ''
  const can = useCan()('notify:config')
  const meta = useQuery({
    queryKey: ['notifications', 'meta'],
    queryFn: api.notifications.meta,
  })
  const roles = useQuery({
    queryKey: ['tenant-roles', tid, 'all'],
    queryFn: () => api.tenants.roles(tid, ALL),
    enabled: !!tid,
  })
  const members = useQuery({
    queryKey: ['members', tid, 'all'],
    queryFn: () => api.tenants.members(tid, ALL),
    enabled: !!tid,
  })
  const types = (meta.data?.event_types ?? []).map((e) => ({
    value: e.code,
    label: eventLabel(e.code),
  }))
  const filters: FilterDef[] = [
    searchFilter(t('notify.sub.search')),
    {
      type: 'select',
      name: 'event_type',
      label: t('notify.allTypes'),
      options: types,
    },
    {
      type: 'select',
      name: 'is_active',
      label: t('notify.sub.allStatus'),
      options: boolOptions(t('notify.sub.enabled'), t('notify.sub.disabled')),
    },
  ]
  const lp = useListParams(filters)
  const q = useQuery({
    queryKey: ['notify-subs', 'page', lp.query],
    queryFn: () => api.notifications.subscriptions(lp.query),
  })
  const s = useCrudState<Subscription>()
  const keys = [['notify-subs']]
  const create = useApiMutation(
    api.notifications.createSubscription,
    keys,
    t('notify.sub.created')
  )
  const update = useApiMutation(
    (b: SubscriptionIn & { id: string }) =>
      api.notifications.updateSubscription(b.id, b),
    keys,
    t('notify.sub.updated')
  )
  const remove = useApiMutation(
    api.notifications.removeSubscription,
    keys,
    t('notify.sub.deleted')
  )
  const roleName = new Map(
    roles.data?.data.map((r) => [r.id, r.name] as const) ?? []
  )
  const userName = new Map(
    members.data?.data.map((m) => [m.user_id, m.email] as const) ?? []
  )
  const toBody = (v: Values): SubscriptionIn => ({
    name: v.name as string,
    event_type: v.event_type as string,
    role_ids: (v.role_ids as string[]) ?? [],
    user_ids: (v.user_ids as string[]) ?? [],
    channels: (v.channels as string[])?.length
      ? (v.channels as string[])
      : ['in_app'],
    is_active: !!v.is_active,
  })
  const chips = (xs: string[], names: Map<string, string>) =>
    xs.map((x) => (
      <Badge key={x} variant='outline' className='me-1'>
        {names.get(x) ?? x.slice(0, 8)}
      </Badge>
    ))
  return (
    <Page
      title={t('notify.sub.title')}
      description={t('notify.sub.desc')}
      actions={
        can && (
          <Button onClick={s.openCreate}>
            <Plus /> {t('notify.sub.new')}
          </Button>
        )
      }
    >
      <DataTable
        rows={q.data?.data}
        total={q.data?.count}
        params={lp}
        filters={filters}
        loading={q.isLoading}
        rowKey={(r) => r.id}
        columns={[
          {
            header: t('notify.sub.name'),
            sortKey: 'name',
            cell: (r) => r.name,
          },
          {
            header: t('notify.type'),
            sortKey: 'event_type',
            cell: (r) => eventLabel(r.event_type),
          },
          {
            header: t('notify.sub.roles'),
            cell: (r) => chips(r.role_ids, roleName),
          },
          {
            header: t('notify.sub.users'),
            cell: (r) => chips(r.user_ids, userName),
          },
          {
            header: t('notify.sub.channels'),
            cell: (r) =>
              r.channels.map((c) => t(`notify.channel.${c}`)).join(', '),
          },
          {
            header: t('notify.sub.status'),
            cell: (r) =>
              r.is_active ? (
                <Badge>{t('notify.sub.enabled')}</Badge>
              ) : (
                <Badge variant='secondary'>{t('notify.sub.disabled')}</Badge>
              ),
          },
          {
            header: '',
            className: 'w-24',
            cell: (r) =>
              can && (
                <RowActions
                  onEdit={() => s.openEdit(r)}
                  onDelete={() => s.openDelete(r)}
                />
              ),
          },
        ]}
      />
      <FormDialog
        open={s.formOpen}
        onOpenChange={(o) => !o && s.closeForm()}
        title={s.editing ? t('notify.sub.edit') : t('notify.sub.new')}
        fields={[
          { name: 'name', label: t('notify.sub.name'), required: true },
          {
            name: 'event_type',
            label: t('notify.type'),
            type: 'select',
            required: true,
            options: types,
          },
          {
            name: 'role_ids',
            label: t('notify.sub.roles'),
            type: 'multi',
            options:
              roles.data?.data.map((r) => ({ value: r.id, label: r.name })) ??
              [],
          },
          {
            name: 'user_ids',
            label: t('notify.sub.users'),
            type: 'multi',
            options:
              members.data?.data.map((m) => ({
                value: m.user_id,
                label: m.email,
              })) ?? [],
          },
          {
            name: 'channels',
            label: t('notify.sub.channels'),
            type: 'multi',
            options: (meta.data?.channels ?? []).map((c) => ({
              value: c.code,
              label: t(`notify.channel.${c.code}`),
            })),
          },
          {
            name: 'is_active',
            label: t('notify.sub.enabled'),
            type: 'checkbox',
          },
        ]}
        initial={{
          name: s.editing?.name ?? '',
          event_type: s.editing?.event_type ?? '',
          role_ids: s.editing?.role_ids ?? [],
          user_ids: s.editing?.user_ids ?? [],
          channels: s.editing?.channels ?? ['in_app'],
          is_active: s.editing?.is_active ?? true,
        }}
        onSubmit={(v) =>
          s.editing
            ? update.mutateAsync({ id: s.editing.id, ...toBody(v) })
            : create.mutateAsync(toBody(v))
        }
      />
      <ConfirmDialog
        open={!!s.deleting}
        onOpenChange={(o) => !o && s.closeDelete()}
        title={t('notify.sub.delete')}
        desc={t('notify.sub.deleteDesc', { name: s.deleting?.name })}
        destructive
        confirmText={t('common.delete')}
        handleConfirm={() =>
          s.deleting &&
          remove.mutate(s.deleting.id, { onSuccess: s.closeDelete })
        }
      />
    </Page>
  )
}
