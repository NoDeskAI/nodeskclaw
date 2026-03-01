import { ref } from 'vue'

export interface ToastAction {
  label: string
  onClick: () => void
}

export interface ToastOptions {
  action?: ToastAction
  duration?: number
}

export interface ToastItem {
  id: number
  message: string
  type: 'success' | 'error' | 'info'
  action?: ToastAction
}

const toasts = ref<ToastItem[]>([])
let nextId = 0

function addToast(message: string, type: ToastItem['type'], options?: ToastOptions) {
  const id = nextId++
  toasts.value.push({ id, message, type, action: options?.action })
  setTimeout(() => {
    removeToast(id)
  }, options?.duration ?? 3000)
}

function removeToast(id: number) {
  toasts.value = toasts.value.filter(t => t.id !== id)
}

export function useToast() {
  return {
    toasts,
    success: (message: string, options?: ToastOptions) => addToast(message, 'success', options),
    error: (message: string, options?: ToastOptions) => addToast(message, 'error', options),
    info: (message: string, options?: ToastOptions) => addToast(message, 'info', options),
    remove: removeToast,
  }
}
