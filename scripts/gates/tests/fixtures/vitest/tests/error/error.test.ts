import {describe, expect, it} from 'vitest'

describe('SC-001 真的爆掉', () => {
  it('不是哨兵的錯誤逸出', () => {
    const missing = undefined as unknown as {value: string}
    expect(missing.value).toBe('x')
  })
})
