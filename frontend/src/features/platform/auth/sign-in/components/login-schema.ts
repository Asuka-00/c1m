/** 登录表单校验。 */
import { z } from 'zod'
import { t } from '@/i18n'

/** 登录表单校验：仅接受用户名。 */
export const formSchema = z.object({
  // 仅支持用户名登录（不接受邮箱）；消息写成函数以跟随当前语言
  login: z
    .string()
    .trim()
    .min(1, { error: () => t('auth.loginRequired') })
    .regex(/^[A-Za-z0-9_.-]{3,50}$/, { error: () => t('auth.loginInvalid') }),
  password: z.string().min(1, { error: () => t('auth.passwordRequired') }),
})
