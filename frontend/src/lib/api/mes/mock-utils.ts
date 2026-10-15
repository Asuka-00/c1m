/** mock 公共工具：构造与后端同形的 axios 错误（response.data.detail）。 */
import { AxiosError, AxiosHeaders } from 'axios'

export function apiError(status: number, detail: unknown) {
  return new AxiosError('mock', 'ERR_BAD_REQUEST', undefined, undefined, {
    status,
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
    data: { detail },
  })
}

/** D86 补充二：mock 没有响应头，用「最近一次幂等写的响应头」最小表示。
 *  回放成功响应时为 {'Idempotent-Replayed': 'true'}，首次执行为 {}；仅供测试断言，业务代码不得依赖。 */
let lastHeaders: Record<string, string> = {}
export const mockIdemHeaders = () => ({ ...lastHeaders })
export const setMockReplayed = (replayed: boolean) => {
  lastHeaders = replayed ? { 'Idempotent-Replayed': 'true' } : {}
}
