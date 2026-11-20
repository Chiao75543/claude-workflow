import {describe, expect, it} from 'vitest'
import {nothing} from '../../src/does-not-exist'

describe('SC-002 import 不到的那個檔', () => {
  it('根本沒被收集到', () => {
    expect(nothing()).toBe('x')
  })
})
