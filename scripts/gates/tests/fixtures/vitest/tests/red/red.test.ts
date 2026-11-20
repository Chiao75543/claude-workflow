import {describe, expect, it} from 'vitest'
import {returnsSentinel, throwsSentinel} from '../../src/stub'

describe('SC-001 回傳哨兵值的 stub → 斷言有評估到', () => {
  it.each([
    ['a', 'A'],
    ['b', 'B'],
    ['c', 'C'],
  ])('%s → %s', (_input, expected) => {
    expect(returnsSentinel()).toBe(expected)
  })
})

describe('SC-002 丟哨兵錯誤的 stub', () => {
  it('錯誤直接逸出 → 斷言沒跑到', () => {
    expect(throwsSentinel()).toBe('x')
  })

  it('包在 toThrow 裡 → 斷言有評估到', () => {
    expect(() => throwsSentinel()).toThrow('離線')
  })
})
