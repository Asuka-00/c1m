/**
 * 按批次打开操作台或履历的链接。
 * 批次履历（mes-lot-trace）只是 mes-lot-history 下的页签，没有独立路由，
 * 不能拼成 mes/lot-trace（会 404），必须跳 mes/lot-history 并带 tab。
 */
export type LotPage = 'lot-console' | 'lot-trace'

export function lotPageLink(page: LotPage, lot: unknown) {
  const id = String(lot)
  return page === 'lot-trace'
    ? {
        to: '/$' as const,
        params: { _splat: 'mes/lot-history' },
        search: { tab: 'mes-lot-trace', lot: id } as never,
      }
    : {
        to: '/$' as const,
        params: { _splat: 'mes/lot-console' },
        search: { lot: id } as never,
      }
}
