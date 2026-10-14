/**
 * KEYED_ENTITIES 通用 CRUD 的 mock（D87 补充二，先用于 alarm_code）：
 * - 缺 key → 422 missing（loc header，D81：先于请求体 / 404）；
 * - 同 key 不同请求体 → 422 value_error ctx.reason=reused；
 * - 只缓存 2xx（D86），回放带 Idempotent-Replayed（D86 补充二）。
 */
import { apiError, setMockReplayed } from './mock-utils'

type Row = Record<string, unknown> & { id: string }

export function createKeyedCrudMock(entity: string, seed: Row[] = []) {
  let rows: Row[] = structuredClone(seed)
  const idem = new Map<string, { sig: string; out: unknown }>()
  let n = 0
  const keyed = <T>(key: string | undefined, sig: string, f: () => T): T => {
    setMockReplayed(false)
    if (!key)
      throw apiError(422, [
        {
          loc: ['header', 'Idempotency-Key'],
          type: 'missing',
          code: 'missing',
          msg: 'Idempotency-Key: field required',
        },
      ])
    const hit = idem.get(key)
    if (hit) {
      if (hit.sig !== sig)
        throw apiError(422, [
          {
            loc: ['header', 'Idempotency-Key'],
            type: 'value_error',
            code: 'value_error',
            msg: 'Idempotency-Key reused with a different request',
            ctx: { reason: 'reused' },
          },
        ])
      setMockReplayed(true)
      return structuredClone(hit.out) as T
    }
    const out = f()
    idem.set(key, { sig, out: structuredClone(out) })
    return out
  }
  const find = (id: string) => {
    const r = rows.find((x) => x.id === id)
    if (!r) throw apiError(404, `${entity} not found`)
    return r
  }
  const sigOf = (op: string, id: string, body?: object) =>
    `${op}|${id}|${JSON.stringify(body ?? null)}`
  return {
    rows: () => structuredClone(rows),
    reset: () => {
      rows = structuredClone(seed)
      idem.clear()
    },
    create: (body: Record<string, unknown>, key?: string) =>
      keyed(key, sigOf('create', '', body), () => {
        const r = { ...body, id: `${entity}-${++n}` }
        rows.push(r)
        return structuredClone(r)
      }),
    update: (id: string, body: Record<string, unknown>, key?: string) =>
      keyed(key, sigOf('update', id, body), () => {
        const r = find(id)
        Object.assign(r, body)
        return structuredClone(r)
      }),
    remove: (id: string, key?: string) =>
      keyed(key, sigOf('remove', id), () => {
        find(id)
        rows = rows.filter((x) => x.id !== id)
        return null
      }),
  }
}
