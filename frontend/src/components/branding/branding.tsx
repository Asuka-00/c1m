import { useEffect } from 'react'
import { t } from '@/i18n'
import { Logo } from '@/assets/logo'
import { applyAccent } from '@/lib/accent'
import type { Branding } from '@/lib/branding'
import { cn } from '@/lib/utils'

/** Applies branding to the document: title, favicon and accent colour. */
export function BrandingHead({
  branding,
  page,
}: {
  branding: Branding
  page?: string
}) {
  const { appName, favicon, logo, primaryColor } = branding
  useEffect(() => applyAccent(primaryColor), [primaryColor])
  useEffect(() => {
    document.title = page ? `${page} · ${appName}` : appName
  }, [appName, page])
  useEffect(() => {
    const href = favicon ?? logo
    if (!href) return
    let link = document.querySelector<HTMLLinkElement>("link[rel~='icon']")
    if (!link) {
      link = document.createElement('link')
      link.rel = 'icon'
      document.head.appendChild(link)
    }
    link.href = href
  }, [favicon, logo])
  return null
}

export function BrandLogo({
  branding,
  className,
}: {
  branding: Branding
  className?: string
}) {
  return branding.logo ? (
    <img
      src={branding.logo}
      alt={branding.appName}
      className={cn('size-8 rounded-md object-contain', className)}
    />
  ) : (
    <Logo className={className} />
  )
}

export function BrandFooter({
  branding,
  className,
}: {
  branding: Branding
  className?: string
}) {
  if (!branding.footer && !branding.supportUrl) return null
  return (
    <footer
      className={cn(
        'flex flex-wrap items-center justify-center gap-x-3 gap-y-1 py-3 text-xs text-muted-foreground',
        className
      )}
      data-testid='brand-footer'
    >
      {branding.footer && (
        <span className='whitespace-pre-line'>{branding.footer}</span>
      )}
      {branding.supportUrl && (
        <a
          href={branding.supportUrl}
          target='_blank'
          rel='noreferrer'
          className='underline underline-offset-2 hover:text-foreground'
        >
          {t('config.support')}
        </a>
      )}
    </footer>
  )
}
