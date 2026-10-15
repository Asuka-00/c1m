import { describe, expect, it } from 'vitest'
import { daysUntil } from './due'

describe('daysUntil', () => {
  const today = new Date(2026, 9, 12, 23, 30)
  it('counts calendar days from today', () => {
    expect(daysUntil('2026-10-12', today)).toBe(0)
    expect(daysUntil('2026-10-15', today)).toBe(3)
    expect(daysUntil('2026-10-01T00:00:00', today)).toBe(-11)
  })
})
