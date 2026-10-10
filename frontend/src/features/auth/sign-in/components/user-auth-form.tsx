import { useState } from 'react'
import { z } from 'zod'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { t } from '@/i18n'
import { Loader2, LogIn } from 'lucide-react'
import { toast } from 'sonner'
import { useAuthStore } from '@/stores/auth-store'
import { api } from '@/lib/api'
import { errorMessage } from '@/lib/api/client'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { PasswordInput } from '@/components/password-input'

const formSchema = z.object({
  // username OR email; messages are functions so they follow the current language
  login: z
    .string()
    .trim()
    .min(1, { error: () => t('auth.loginRequired') })
    .refine(
      (v) =>
        v.includes('@')
          ? z.email().safeParse(v).success
          : /^[A-Za-z0-9_.-]{3,50}$/.test(v),
      { error: () => t('auth.loginInvalid') }
    ),
  password: z.string().min(1, { error: () => t('auth.passwordRequired') }),
})

interface UserAuthFormProps extends React.HTMLAttributes<HTMLFormElement> {
  redirectTo?: string
}

/** Sign in against POST /api/v1/login/access-token. */
export function UserAuthForm({
  className,
  redirectTo,
  ...props
}: UserAuthFormProps) {
  const [isLoading, setIsLoading] = useState(false)
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { setAccessToken, setTenantId } = useAuthStore()

  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: { login: '', password: '' },
  })

  async function onSubmit(data: z.infer<typeof formSchema>) {
    setIsLoading(true)
    try {
      const { access_token } = await api.login(data.login, data.password)
      setAccessToken(access_token)
      setTenantId(null)
      qc.clear()
      // multiple tenants -> preselect the first one (sent as X-Tenant-ID)
      const mine = await api.myTenants()
      if (mine.count > 1)
        setTenantId(
          (mine.data.find((t) => t.tenant.slug === 'default') ?? mine.data[0]!)
            .tenant.id
        )
      const me = await api.me()
      toast.success(t('auth.welcome', { name: me.full_name || me.email }))
      navigate({ to: redirectTo || '/', replace: true })
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className={cn('grid gap-3', className)}
        {...props}
      >
        <FormField
          control={form.control}
          name='login'
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('auth.loginLabel')}</FormLabel>
              <FormControl>
                <Input
                  placeholder={t('auth.loginPlaceholder')}
                  autoComplete='username'
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name='password'
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('common.password')}</FormLabel>
              <FormControl>
                <PasswordInput placeholder='********' {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button className='mt-2' disabled={isLoading}>
          {isLoading ? <Loader2 className='animate-spin' /> : <LogIn />}
          {t('auth.signIn')}
        </Button>
      </form>
    </Form>
  )
}
