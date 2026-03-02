import { ref } from 'vue'

export type ToastType = 'success' | 'error' | 'info' | 'warning'

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
  type: ToastType
  action?: ToastAction
  leaving: boolean
}

const toasts = ref<ToastItem[]>([])
let nextId = 0

function addToast(message: string, type: ToastType, options?: ToastOptions) {
  const id = nextId++
  toasts.value.push({ id, message, type, action: options?.action, leaving: false })
  setTimeout(() => {
    dismiss(id)
  }, options?.duration ?? 3000)
}

function dismiss(id: number) {
  const item = toasts.value.find(t => t.id === id)
  if (!item) return
  item.leaving = true
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }, 300)
}

export function useToast() {
  return {
    toasts,
    success: (message: string, options?: ToastOptions) => addToast(message, 'success', options),
    error: (message: string, options?: ToastOptions) => addToast(message, 'error', options),
    info: (message: string, options?: ToastOptions) => addToast(message, 'info', options),
    warning: (message: string, options?: ToastOptions) => addToast(message, 'warning', options),
    dismiss,
  }
}
