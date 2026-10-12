import { LANGUAGES } from '@/i18n'
import { Check, Languages } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

/** 语言切换器（由 i18next 检测器缓存持久化到 localStorage）。 */
export function LanguageSwitch() {
  const { t, i18n } = useTranslation()
  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button
          variant='ghost'
          size='sm'
          className='gap-1'
          data-testid='language-switch'
        >
          <Languages className='size-4' />
          <span>{t(`lang.${i18n.resolvedLanguage}`)}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align='end'>
        {LANGUAGES.map((l) => (
          <DropdownMenuItem key={l} onClick={() => i18n.changeLanguage(l)}>
            {t(`lang.${l}`)}
            <Check
              className={
                i18n.resolvedLanguage === l
                  ? 'ms-auto size-4'
                  : 'invisible ms-auto size-4'
              }
            />
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
