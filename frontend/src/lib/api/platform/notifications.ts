/** 站内通知接口：我的通知、未读汇总、已读、事件元数据、订阅配置。 */
import { del, get, post, put, type ListQuery } from '../request'
import type { Paged } from '../types'

/** 通知严重度。 */
export type Severity = 'info' | 'warning' | 'critical'

/** 我的通知（含个人已读状态）。 */
export interface Notification {
  id: string
  event_type: string
  event_label: string
  severity: Severity
  title: string
  body: string | null
  params: Record<string, unknown>
  object_type: string | null
  object_id: string | null
  object_code: string | null
  link: string | null
  created_at: string
  read_at: string | null
  is_read: boolean
}

/** 未读数 + 最新通知。 */
export interface NotificationSummary {
  unread: number
  latest: Notification[]
}

/** 已登记的事件类型。 */
export interface EventType {
  code: string
  label: string
  severity: Severity
  object_type: string | null
}

/** 通知元数据：事件类型、渠道、严重度。 */
export interface NotificationMeta {
  event_types: EventType[]
  channels: { code: string; label: string }[]
  severities: Severity[]
}

/** 通知订阅：事件类型 → 角色 / 用户。 */
export interface Subscription {
  id: string
  name: string
  event_type: string
  role_ids: string[]
  user_ids: string[]
  channels: string[]
  is_active: boolean
  created_at: string
  updated_at: string
}

/** 订阅写入体。 */
export type SubscriptionIn = Omit<
  Subscription,
  'id' | 'created_at' | 'updated_at'
>

/** 站内通知接口。 */
export const notificationsApi = {
  list: (q: ListQuery) => get<Paged<Notification>>('/notifications', q),
  summary: () => get<NotificationSummary>('/notifications/summary'),
  read: (ids?: string[]) =>
    post<{ updated: number }>('/notifications/read', ids ? { ids } : {}),
  meta: () => get<NotificationMeta>('/notification-meta'),
  subscriptions: (q: ListQuery) =>
    get<Paged<Subscription>>('/notification-subscriptions', q),
  createSubscription: (b: SubscriptionIn) =>
    post<Subscription>('/notification-subscriptions', b),
  updateSubscription: (id: string, b: SubscriptionIn) =>
    put<Subscription>(`/notification-subscriptions/${id}`, b),
  removeSubscription: (id: string) =>
    del<{ ok: boolean }>(`/notification-subscriptions/${id}`),
}
