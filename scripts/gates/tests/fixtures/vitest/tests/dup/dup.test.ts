import {describe, expect, it} from 'vitest'
import {returnsSentinel} from '../../src/stub'

describe('SC-001 測試名重複', () => {
  it.each([['a'], ['b']])('標題沒帶參數', (input) => {
    expect(returnsSentinel()).toBe(input)
  })
})
