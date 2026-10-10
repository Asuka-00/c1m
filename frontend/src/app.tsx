import { type AnyRouter, RouterProvider } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

/** Re-mounts the router when the language changes, so every component —
 *  including ones that use the plain `t` helper — renders in the new language. */
export function App({ router }: { router: AnyRouter }) {
  const { i18n } = useTranslation()
  return <RouterProvider key={i18n.resolvedLanguage} router={router} />
}
