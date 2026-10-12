/** File uploads. */
import { http } from '../client'
import type { UploadedFile } from '../types'

export const filesApi = {
  upload: (file: File, scope: 'tenant' | 'platform' = 'tenant') => {
    const fd = new FormData()
    fd.append('file', file)
    return http
      .post<UploadedFile>('/files/upload', fd, { params: { scope } })
      .then((r) => r.data)
  },
}
