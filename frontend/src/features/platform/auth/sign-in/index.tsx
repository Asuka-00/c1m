/** 登录页。 */
import { useSearch } from '@tanstack/react-router'
import { t } from '@/i18n'
import { AuthLayout } from '@/features/platform/auth/auth-layout'
import { UserAuthForm } from '@/features/platform/auth/sign-in/components/user-auth-form'

/** 登录页：品牌布局 + 登录表单。 */
export function SignIn() {
  const { redirect } = useSearch({ from: '/(auth)/sign-in' })
  return (
    <AuthLayout>
      <div className='mb-8 space-y-1.5'>
        <h2 className='text-2xl font-semibold tracking-tight'>
          {t('auth.signIn')}
        </h2>
        <p className='text-sm text-muted-foreground'>{t('auth.signInDesc')}</p>
      </div>
      <UserAuthForm redirectTo={redirect} />
    </AuthLayout>
  )
}
