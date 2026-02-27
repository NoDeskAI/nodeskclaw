import { ref } from 'vue'

export interface ToastAction {
  label: string
  onClick: () => void
}

export interface ToastItem {
  id: number
  type: 'success' | 'error' | 'info'
  message: string
  action?: ToastAction
}

const toasts = ref<ToastItem[]>([])
let nextId = 0

interface ToastOptions {
  duration?: number
  action?: ToastAction
}

function add(type: ToastItem['type'], message: string, opts?: ToastOptions) {
  const id = nextId++
  const duration = opts?.duration ?? (type === 'error' ? 6000 : 4000)
  toasts.value.push({ id, type, message, action: opts?.action })
  if (opts?.action) {
    setTimeout(() => remove(id), 8000)
  } else {
    setTimeout(() => remove(id), duration)
  }
}

function remove(id: number) {
  toasts.value = toasts.value.filter(t => t.id !== id)
}

export function useToast() {
  return {
    toasts,
    success: (msg: string, opts?: ToastOptions) => add('success', msg, opts),
    error: (msg: string, opts?: ToastOptions) => add('error', msg, opts),
    info: (msg: string, opts?: ToastOptions) => add('info', msg, opts),
    remove,
  }
}
