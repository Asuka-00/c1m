import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { ChangeResult } from './change-actions'

describe('ChangeResult', () => {
  it('列出切换与沿用旧版的批次', async () => {
    const s = await render(
      <ChangeResult
        row={{
          id: '1',
          code: 'ECN1',
          result: { version: 2, refs: 3, switched: ['L1'], kept: ['L2'] },
        }}
      />
    )
    await expect.element(s.getByText(/L1/)).toBeInTheDocument()
    await expect.element(s.getByText(/L2/)).toBeInTheDocument()
  })
  it('未生效时不显示', async () => {
    const s = await render(<ChangeResult row={{ id: '1', code: 'E' }} />)
    expect(s.container.textContent).toBe('')
  })
})
