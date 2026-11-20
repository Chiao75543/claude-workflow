import {describe, expect, it} from 'vitest'
import {returnsSentinel} from '../../src/stub'

describe('SC-001 載得進來的那個檔', () => {
  it('有跑、有紅', () => {
    expect(returnsSentinel()).toBe('x')
  })
})
