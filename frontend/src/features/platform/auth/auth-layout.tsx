/** 登录相关页面的布局。 */
import { useEffect } from 'react'
import { useSearch } from '@tanstack/react-router'
import {
  rememberBrandTenant,
  rememberedBrandTenant,
  useBranding,
} from '@/lib/branding'
import { BrandFooter, BrandingHead } from '@/components/branding/branding'
import { LanguageSwitch } from '@/components/language-switch'
import { ThemeSwitch } from '@/components/theme-switch'
import { BrandMark, BrandPanel } from './brand-panel'

type AuthLayoutProps = {
  children: React.ReactNode
}

/** 登录页布局：按 ?tenant=<slug>（会记住）或平台默认值显示品牌。 */
export function AuthLayout({ children }: AuthLayoutProps) {
  const search = useSearch({ strict: false }) as Record<string, unknown>
  const fromUrl = typeof search.tenant === 'string' ? search.tenant : null
  const slug = fromUrl ?? rememberedBrandTenant()
  useEffect(() => rememberBrandTenant(fromUrl), [fromUrl])
  const branding = useBranding(slug)
  return (
    <div className='grid min-h-svh lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]'>
      <BrandingHead branding={branding} />
      <BrandPanel branding={branding} />
      <div className='flex min-w-0 flex-col'>
        <header className='flex items-center gap-2 p-4'>
          <h1 className='min-w-0 lg:invisible' data-testid='brand-name'>
            <BrandMark branding={branding} />
          </h1>
          <div className='ms-auto flex items-center gap-1'>
            <LanguageSwitch />
            <ThemeSwitch />
          </div>
        </header>
        <main className='flex flex-1 items-center justify-center px-6 py-10'>
          <div className='w-full max-w-sm'>{children}</div>
        </main>
        <BrandFooter branding={branding} />
      </div>
    </div>
  )
}
