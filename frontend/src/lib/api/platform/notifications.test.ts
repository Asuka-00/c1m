import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http } from '../client'
import { notificationsApi } from './notifications'

const post = vi.spyOn(http, 'post')
const put = vi.spyOn(http, 'put')
const row = {
  id: 'sub-1',
  tenant_id: 't',
  created_at: 'c',
  updated_at: 'u',
  name: 'n',
  event_type: 'lot.hold',
  role_ids: ['r'],
  user_ids: [],
  channels: ['in_app'],
  is_active: false,
}
const WRITABLE = [
  'channels',
  'event_type',
  'is_active',
  'name',
  'role_ids',
  'user_ids',
]

beforeEach(() => {
  post.mockReset().mockResolvedValue({ data: {} })
  put.mockReset().mockResolvedValue({ data: {} })
})

describe('通知订阅请求体（SubscriptionIn extra=forbid）', () => {
  it('更新：整行传入也只发可写字段，id 只在路径里', async () => {
    await notificationsApi.updateSubscription('sub-1', row as never)
    const [url, body] = put.mock.calls[0]
    expect(url).toBe('/notification-subscriptions/sub-1')
    expect(Object.keys(body as object).sort()).toEqual(WRITABLE)
    expect(body).toMatchObject({ is_active: false, user_ids: [] })
  })
  it('新建：同样裁剪多余字段', async () => {
    await notificationsApi.createSubscription(row as never)
    const [url, body] = post.mock.calls[0]
    expect(url).toBe('/notification-subscriptions')
    expect(Object.keys(body as object).sort()).toEqual(WRITABLE)
  })
})
