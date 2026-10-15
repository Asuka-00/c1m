import { beforeEach, describe, expect, it } from 'vitest'
import { useAuthStore } from './auth-store'

describe('以租户身份进入：令牌切换', () => {
  beforeEach(() => {
    localStorage.clear()
    useAuthStore.setState({
      accessToken: 'orig',
      tenantId: null,
      impersonating: null,
      originalToken: null,
    })
  })
  it('进入时保存原令牌并改用模拟令牌，退出时恢复', () => {
    const s = useAuthStore.getState()
    s.startImpersonation({ id: 't1', name: 'Acme' }, 'imp')
    let st = useAuthStore.getState()
    expect(st.accessToken).toBe('imp')
    expect(st.tenantId).toBe('t1')
    expect(st.originalToken).toBe('orig')
    expect(localStorage.getItem('fsft_orig_token')).toBe('orig')
    // 连续进入另一租户仍保留最初的平台令牌
    st.startImpersonation({ id: 't2', name: 'B' }, 'imp2')
    expect(useAuthStore.getState().originalToken).toBe('orig')
    expect(useAuthStore.getState().endImpersonation()?.id).toBe('t2')
    st = useAuthStore.getState()
    expect(st.accessToken).toBe('orig')
    expect(st.tenantId).toBeNull()
    expect(st.impersonating).toBeNull()
    expect(localStorage.getItem('fsft_token')).toBe('orig')
    expect(localStorage.getItem('fsft_orig_token')).toBeNull()
  })
  it('未模拟时退出无副作用', () => {
    expect(useAuthStore.getState().endImpersonation()).toBeNull()
    expect(useAuthStore.getState().accessToken).toBe('orig')
  })
})
