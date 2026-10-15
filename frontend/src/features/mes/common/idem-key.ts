import { useState } from 'react'
import { newEventId } from './event-id'

/**
 * 一次用户操作的 Idempotency-Key（D57/D80）：
 * - 同一次操作重试（请求体不变）沿用同一个 key，服务端重放原响应；
 * - 请求体变了换新 key，避免 422 idempotency_key_reused；
 * - 操作成功后调用 done()，下一次操作换新 key。
 */
export class OperationKey {
  private cur: { sig: string; key: string } | null = null
  constructor(private readonly gen: () => string = newEventId) {}
  /** 按请求体签名取 key。 */
  key(sig: string): string {
    if (!this.cur || this.cur.sig !== sig) this.cur = { sig, key: this.gen() }
    return this.cur.key
  }
  /** 操作成功：作废当前 key。 */
  done(): void {
    this.cur = null
  }
}

/** 组件内使用的操作 key（每个对话框 / 操作入口一个）。 */
export function useOperationKey(): OperationKey {
  const [k] = useState(() => new OperationKey())
  return k
}
