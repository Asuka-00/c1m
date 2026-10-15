/** 个人设置页面。 */
import { useState } from 'react'
import { t } from '@/i18n'
import { api, type User } from '@/lib/api'
import { useApiMutation, useMe } from '@/lib/api/hooks'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Page } from '@/components/crud'
import { LanguageSwitch } from '@/components/language-switch'
import { PasswordInput } from '@/components/password-input'

/** 个人设置：资料、密码与语言。 */
export default function SettingsPage() {
  const { data: me } = useMe()
  const [pw, setPw] = useState({
    current_password: '',
    new_password: '',
    confirm: '',
  })
  const changePw = useApiMutation(
    api.updatePassword,
    [],
    t('settings.passwordChanged')
  )
  return (
    <Page title={t('settings.title')} description={t('settings.desc')}>
      <div className='grid gap-4 lg:grid-cols-2'>
        {me && (
          <ProfileCard
            key={me.id + (me.email ?? '') + (me.full_name ?? '')}
            me={me}
          />
        )}
        <Card>
          <CardHeader>
            <CardTitle>{t('common.password')}</CardTitle>
            <CardDescription>{t('settings.passwordHint')}</CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className='grid gap-4'
              onSubmit={(e) => {
                e.preventDefault()
                if (pw.new_password !== pw.confirm) return
                changePw.mutate(
                  {
                    current_password: pw.current_password,
                    new_password: pw.new_password,
                  },
                  {
                    onSuccess: () =>
                      setPw({
                        current_password: '',
                        new_password: '',
                        confirm: '',
                      }),
                  }
                )
              }}
            >
              {(['current_password', 'new_password', 'confirm'] as const).map(
                (k) => (
                  <div key={k} className='grid gap-2'>
                    <Label htmlFor={k}>
                      {k === 'confirm'
                        ? t('settings.confirmPassword')
                        : k === 'new_password'
                          ? t('settings.newPassword')
                          : t('settings.currentPassword')}
                    </Label>
                    <PasswordInput
                      id={k}
                      value={pw[k]}
                      onChange={(e) => setPw({ ...pw, [k]: e.target.value })}
                    />
                  </div>
                )
              )}
              {pw.confirm && pw.new_password !== pw.confirm && (
                <p className='text-sm text-destructive'>
                  {t('settings.mismatch')}
                </p>
              )}
              <Button
                className='justify-self-start'
                disabled={changePw.isPending}
              >
                {t('settings.changePassword')}
              </Button>
            </form>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t('settings.language')}</CardTitle>
            <CardDescription>{t('settings.languageDesc')}</CardDescription>
          </CardHeader>
          <CardContent>
            <LanguageSwitch />
          </CardContent>
        </Card>
      </div>
    </Page>
  )
}

function ProfileCard({ me }: { me: User }) {
  const [fullName, setFullName] = useState(me.full_name ?? '')
  const [email, setEmail] = useState(me.email ?? '')
  const save = useApiMutation(
    api.updateMe,
    [['me']],
    t('settings.profileUpdated')
  )
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('settings.profile')}</CardTitle>
        <CardDescription>
          {me.is_superuser
            ? t('settings.superAccount')
            : t('settings.regularAccount')}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className='grid gap-4'
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate({
              full_name: fullName || null,
              email: email.trim() || null,
            })
          }}
        >
          <div className='grid gap-2'>
            <Label htmlFor='username'>{t('common.username')}</Label>
            <Input id='username' value={me.username} readOnly disabled />
          </div>
          <div className='grid gap-2'>
            <Label htmlFor='full_name'>{t('common.fullName')}</Label>
            <Input
              id='full_name'
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
          </div>
          <div className='grid gap-2'>
            <Label htmlFor='email'>{t('common.email')}</Label>
            <Input
              id='email'
              type='email'
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <Button className='justify-self-start' disabled={save.isPending}>
            {t('settings.saveProfile')}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
