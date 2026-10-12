import { pages as execution } from './execution/pages'
import { pages as planning } from './planning/pages'

/** All MES pages (composition of the domain modules' pages). */
export const pages = { ...planning, ...execution }
