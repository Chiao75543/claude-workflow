// 假實作的兩種寫法:丟哨兵錯誤,或回傳哨兵值。
export function throwsSentinel(): string {
  throw new Error('STUB-NOT-IMPLEMENTED')
}

export function returnsSentinel(): string {
  return 'STUB-NOT-IMPLEMENTED'
}

// 非同步的版本:resolve 哨兵值,或 reject 哨兵錯誤。
export async function resolvesSentinel(): Promise<string> {
  return 'STUB-NOT-IMPLEMENTED'
}

export async function rejectsSentinel(): Promise<string> {
  throw new Error('STUB-NOT-IMPLEMENTED')
}
