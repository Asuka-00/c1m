import { useEffect } from 'react'
import { useSearch } from '@tanstack/react-router'
import {
  rememberBrandTenant,
  rememberedBrandTenant,
  useBranding,
} from '@/lib/branding'
import {
  BrandFooter,
  BrandingHead,
  BrandLogo,
} from '@/components/branding/branding'
import { LanguageSwitch } from '@/components/language-switch'

type AuthLayoutProps = {
  children: React.ReactNode
}

/** Sign-in layout, branded by ?tenant=<slug> (remembered) or platform defaults. */
export function AuthLayout({ children }: AuthLayoutProps) {
  const search = useSearch({ strict: false }) as Record<string, unknown>
  const fromUrl = typeof search.tenant === 'string' ? search.tenant : null
  const slug = fromUrl ?? rememberedBrandTenant()
  useEffect(() => rememberBrandTenant(fromUrl), [fromUrl])
  const branding = useBranding(slug)
  return (
    <div
      className='relative flex min-h-svh flex-col bg-cover bg-center'
      style={
        branding.loginBackground
          ? { backgroundImage: `url(${branding.loginBackground})` }
          : undefined
      }
    >
      <BrandingHead branding={branding} />
      <div className='absolute top-4 right-4'>
        <LanguageSwitch />
      </div>
      <div className='container grid max-w-none flex-1 items-center justify-center'>
        <div className='mx-auto flex w-full flex-col justify-center space-y-2 py-8 sm:p-8'>
          <div className='mb-4 flex flex-col items-center justify-center gap-1'>
            <div className='flex items-center gap-2'>
              <BrandLogo branding={branding} />
              <h1 className='text-xl font-medium' data-testid='brand-name'>
                {branding.appName}
              </h1>
            </div>
            {branding.subtitle && (
              <p className='text-sm text-muted-foreground'>
                {branding.subtitle}
              </p>
            )}
          </div>
          {children}
        </div>
      </div>
      <BrandFooter branding={branding} />
    </div>
  )
}
