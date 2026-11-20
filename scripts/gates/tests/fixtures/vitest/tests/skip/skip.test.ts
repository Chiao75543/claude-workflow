import {describe, expect, it} from 'vitest'
import {returnsSentinel} from '../../src/stub'

describe('SC-001 有測試被跳過', () => {
  it('有跑、有紅', () => {
    expect(returnsSentinel()).toBe('x')
  })

  it.skip('被 skip 的', () => {
    expect(returnsSentinel()).toBe('y')
  })

  it.todo('還沒寫的')
})
