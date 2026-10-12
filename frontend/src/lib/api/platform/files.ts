/** 文件上传接口。 */
import { http } from '../client'
import type { UploadedFile } from '../types'

/** 文件上传接口。 */
export const filesApi = {
  upload: (file: File, scope: 'tenant' | 'platform' = 'tenant') => {
    const fd = new FormData()
    fd.append('file', file)
    return http
      .post<UploadedFile>('/files/upload', fd, { params: { scope } })
      .then((r) => r.data)
  },
}
