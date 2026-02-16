import { ref } from 'vue'

export type NotifyType = 'success' | 'error' | 'info' | 'warning'

export interface NotifyItem {
  id: number
  type: NotifyType
  message: string
  duration: number
  leaving: boolean
}

const queue = ref<NotifyItem[]>([])
let nextId = 0

function push(type: NotifyType, message: string, duration = 2500) {
  const item: NotifyItem = { id: nextId++, type, message, duration, leaving: false }
  queue.value.push(item)

  setTimeout(() => dismiss(item.id), duration)
}

function dismiss(id: number) {
  const item = queue.value.find((n) => n.id === id)
  if (!item) return
  item.leaving = true
  setTimeout(() => {
    queue.value = queue.value.filter((n) => n.id !== id)
  }, 300)
}

export function useNotify() {
  return {
    queue,
    dismiss,
    success: (msg: string, dur?: number) => push('success', msg, dur),
    error: (msg: string, dur?: number) => push('error', msg, dur),
    info: (msg: string, dur?: number) => push('info', msg, dur),
    warning: (msg: string, dur?: number) => push('warning', msg, dur),
  }
}
