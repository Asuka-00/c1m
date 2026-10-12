import { useEffect } from 'react'
import { t } from '@/i18n'
import { Logo } from '@/assets/logo'
import { applyAccent } from '@/lib/accent'
import type { Branding } from '@/lib/branding'
import { cn } from '@/lib/utils'

/** 把品牌应用到文档：标题、favicon 与强调色。 */
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

/** 品牌 Logo：有配置的 Logo 图片时显示图片，否则显示默认图标。 */
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

/** 品牌页脚文本（配置项 footer_text），未配置时不渲染。 */
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
