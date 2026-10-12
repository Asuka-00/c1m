import { useNavigate, useRouter } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

/** Shared, translated error page (code -> errors.<code>.title/desc). */
export function ErrorPage({
  code,
  minimal,
  fullHeight = true,
}: {
  code: 401 | 403 | 404 | 500 | 503
  minimal?: boolean
  fullHeight?: boolean
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { history } = useRouter()
  return (
    <div className={cn(fullHeight ? 'h-svh' : 'h-[70vh]', 'w-full')}>
      <div className='m-auto flex h-full w-full flex-col items-center justify-center gap-2'>
        {!minimal && (
          <h1 className='text-[7rem] leading-tight font-bold'>{code}</h1>
        )}
        <span className='font-medium'>{t(`errors.${code}.title`)}</span>
        <p className='max-w-sm text-center text-muted-foreground'>
          {t(`errors.${code}.desc`)}
        </p>
        {code !== 503 && (
          <div className='mt-6 flex gap-4'>
            <Button variant='outline' onClick={() => history.go(-1)}>
              {t('common.goBack')}
            </Button>
            <Button onClick={() => navigate({ to: '/' })}>
              {t('common.backHome')}
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
