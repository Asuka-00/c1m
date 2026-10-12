import { describe, expect, it } from 'vitest'
import { csvCell, toCsv } from './export-csv'

describe('csv', () => {
  it('escapes special characters', () => {
    expect(csvCell('a,b')).toBe('"a,b"')
    expect(csvCell('say "hi"')).toBe('"say ""hi"""')
    expect(csvCell(null)).toBe('')
    expect(csvCell(3)).toBe('3')
  })
  it('joins rows with CRLF', () => {
    expect(toCsv(['x', 'y'], [[1, 'a']])).toBe('x,y\r\n1,a')
  })
})
