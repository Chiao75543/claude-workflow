import {describe, expect, it} from 'vitest'
import {rejectsSentinel, resolvesSentinel, returnsSentinel} from '../../src/stub'

describe('SC-001 非同步的 stub resolve 哨兵值', () => {
  it('resolves 斷言失敗,訊息裡有哨兵字串', async () => {
    await expect(resolvesSentinel()).resolves.toBe(false)
  })

  it('resolves 斷言失敗,訊息裡沒有哨兵字串', async () => {
    await expect(resolvesSentinel().then((value) => value.length)).resolves.toBe(0)
  })

  it('rejects 斷言失敗:沒有 reject', async () => {
    await expect(resolvesSentinel()).rejects.toThrow('離線')
  })

  it('expect.poll 斷言失敗', async () => {
    await expect.poll(() => returnsSentinel(), {timeout: 100, interval: 20}).toBe('x')
  })
})

describe('SC-002 非同步的 stub reject 哨兵錯誤', () => {
  it('resolves 斷言失敗:被 reject 了', async () => {
    await expect(rejectsSentinel()).resolves.toBe('x')
  })

  it('rejects 斷言失敗:錯誤訊息不對', async () => {
    await expect(rejectsSentinel()).rejects.toThrow('離線')
  })

  it('沒包 expect,錯誤直接逸出', async () => {
    const value = await rejectsSentinel()
    expect(value).toBe('x')
  })
})
