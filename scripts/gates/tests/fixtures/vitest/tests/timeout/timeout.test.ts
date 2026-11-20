import {describe, it} from 'vitest'

describe('SC-001 逾時', () => {
  it('永遠不結束', async () => {
    await new Promise(() => {})
  }, 200)
})
