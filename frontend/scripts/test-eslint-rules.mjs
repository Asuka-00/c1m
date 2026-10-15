// 本地 ESLint 规则自测（RuleTester）：保证「只有图标的按钮必须用 IconButton」守卫有效。
import { RuleTester } from 'eslint'
import tseslint from 'typescript-eslint'
import iconOnlyButton from '../eslint-rules/icon-only-button.js'

const tester = new RuleTester({
  languageOptions: {
    parser: tseslint.parser,
    parserOptions: { ecmaFeatures: { jsx: true } },
  },
})
const err = [{ messageId: 'useIconButton' }]

tester.run('local/icon-only-button', iconOnlyButton, {
  valid: [
    "<Button>{t('common.save')}</Button>",
    "<Button><Plus />{t('common.add')}</Button>",
    "<Button size='sm'><Plus /> Add</Button>",
    "<IconButton label={t('common.edit')}><Pencil /></IconButton>",
    "<Button>{n}</Button>",
  ],
  invalid: [
    { code: "<Button size='icon' aria-label='x'><X /></Button>", errors: err },
    { code: "<Button size='icon-sm'><X /></Button>", errors: err },
    { code: '<Button><Trash2 /></Button>', errors: err },
    {
      code: "<Button><span className='sr-only'>Next</span><ChevronRight /></Button>",
      errors: err,
    },
    { code: '<Button>{open ? <ChevronDown /> : <ChevronRight />}</Button>', errors: err },
  ],
})
console.log('eslint rules OK: local/icon-only-button')
