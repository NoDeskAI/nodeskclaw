import { ref } from 'vue'

export interface ToastItem {
  id: number
  type: 'success' | 'error' | 'info'
  message: string
}

const toasts = ref<ToastItem[]>([])
let nextId = 0

function add(type: ToastItem['type'], message: string, duration = 4000) {
  const id = nextId++
  toasts.value.push({ id, type, message })
  setTimeout(() => remove(id), duration)
}

function remove(id: number) {
  toasts.value = toasts.value.filter(t => t.id !== id)
}

export function useToast() {
  return {
    toasts,
    success: (msg: string) => add('success', msg),
    error: (msg: string) => add('error', msg, 6000),
    info: (msg: string) => add('info', msg),
    remove,
  }
}
