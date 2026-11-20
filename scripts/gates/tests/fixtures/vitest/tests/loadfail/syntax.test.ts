import {describe, expect, it} from 'vitest'
import {returnsSentinel} from '../../src/stub'

describe('SC-002 語法錯的那個檔', () => {
  it('根本沒被收集到', () => {
    expect(returnsSentinel()).toBe('x'
  })
})
