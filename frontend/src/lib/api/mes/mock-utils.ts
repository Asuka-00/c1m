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
