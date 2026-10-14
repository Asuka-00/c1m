import { describe, expect, it } from 'vitest'
import binCsv from './__fixtures__/bin_definition_demo.csv?raw'
import dupCsv from './__fixtures__/map_bad_duplicate_coord.csv?raw'
import unknownCsv from './__fixtures__/map_bad_unknown_bin.csv?raw'
import okCsv from './__fixtures__/map_ok.csv?raw'
import { parseBinSet, previewMap } from './map-csv'

const sets = [parseBinSet(binCsv)]

describe('坐标图 CSV 预览（与 qa/it/fixtures/map 样例一致）', () => {
  it('bin 定义集的名称和版本取自它自己的文件头', () => {
    expect(sets[0]).toMatchObject({ name: 'BINSET-DEMO', version: '1' })
    expect(sets[0].bins.find((b) => b.bin_code === 'E')?.bin_type).toBe('edge')
  })

  it('map_ok：72 行全部通过，两片 6×6', () => {
    const p = previewMap(okCsv, sets)
    expect(p.file_error).toBeNull()
    expect(p.errors).toEqual([])
    expect(p.total_rows).toBe(72)
    expect(p.substrates).toHaveLength(2)
    for (const s of p.substrates)
      expect(s).toMatchObject({ rows: 6, cols: 6, cells: 36 })
    expect(p.header.origin_location).toBe('UL')
  })

  it('坐标重复：数据第 11 行，原始文件第 19 行', () => {
    const p = previewMap(dupCsv, sets)
    expect(p.errors).toEqual([
      expect.objectContaining({
        code: 'duplicate_coord',
        row_no: 11,
        file_line: 19,
      }),
    ])
  })

  it('bin 码未定义：数据第 15 行，原始文件第 23 行', () => {
    const p = previewMap(unknownCsv, sets)
    expect(p.errors).toEqual([
      expect.objectContaining({
        code: 'unknown_bin',
        row_no: 15,
        file_line: 23,
        value: '9',
      }),
    ])
  })

  it('引用的定义集找不到：整份文件报错，不逐行列出', () => {
    const p = previewMap(okCsv, [])
    expect(p.file_error).toBe('unknown_bin_set')
    expect(p.errors).toEqual([])
  })

  it('缺文件头或列名不对：文件级报错', () => {
    expect(
      previewMap('substrate_id,row,col,bin_code\nA,0,0,1', sets).file_error
    ).toBe('missing_header')
    expect(
      previewMap(okCsv.replace('bin_code\n', 'bin\n'), sets).file_error
    ).toBe('bad_column_header')
  })
})
