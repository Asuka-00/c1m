export const SEARCH_DEBOUNCE_MS = 300

export interface FilterOption {
  value: string
  label: string
}

/** Declarative DataTable filter. Every filter is a URL search param of the same
 *  name, sent to the list endpoint as a query param, combined with paging/sort.
 *  - text: free-text (debounced); use name 'q' for the endpoint's keyword search
 *  - select: enumerable values; static `options` or async `loadOptions` */
export type FilterDef =
  | { type: 'text'; name: string; placeholder?: string }
  | {
      type: 'select'
      name: string
      /** label of the "all" entry, e.g. "All roles" */
      label: string
      options?: FilterOption[]
      loadOptions?: () => Promise<FilterOption[]>
      /** react-query key for loadOptions (defaults to ['filter-options', name]) */
      optionsKey?: unknown[]
    }

/** Default for every table: one keyword search box bound to ?q= */
export const DEFAULT_FILTERS: FilterDef[] = [{ type: 'text', name: 'q' }]

export const searchFilter = (placeholder?: string): FilterDef => ({
  type: 'text',
  name: 'q',
  placeholder,
})

export const boolOptions = (yes: string, no: string): FilterOption[] => [
  { value: 'true', label: yes },
  { value: 'false', label: no },
]
