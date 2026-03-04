import { ref } from 'vue'

export interface ConfirmOptions {
  title?: string
  description: string
  confirmText?: string
  cancelText?: string
  variant?: 'default' | 'danger'
}

export interface ConfirmState extends ConfirmOptions {
  visible: boolean
  isAlert: boolean
  resolve: ((value: boolean) => void) | null
}

const state = ref<ConfirmState>({
  visible: false,
  isAlert: false,
  description: '',
  resolve: null,
})

function showConfirm(options: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    state.value = {
      ...options,
      visible: true,
      isAlert: false,
      resolve,
    }
  })
}

function showAlert(options: ConfirmOptions): Promise<void> {
  return new Promise((resolve) => {
    state.value = {
      ...options,
      visible: true,
      isAlert: true,
      resolve: () => resolve(),
    }
  })
}

function handleConfirm() {
  state.value.resolve?.(true)
  state.value.visible = false
}

function handleCancel() {
  state.value.resolve?.(false)
  state.value.visible = false
}

export function useConfirm() {
  return {
    confirm: showConfirm,
    alert: showAlert,
  }
}

export function useConfirmState() {
  return { state, handleConfirm, handleCancel }
}
