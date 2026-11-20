// 假實作的兩種寫法:丟哨兵錯誤,或回傳哨兵值。
export function throwsSentinel(): string {
  throw new Error('STUB-NOT-IMPLEMENTED')
}

export function returnsSentinel(): string {
  return 'STUB-NOT-IMPLEMENTED'
}
