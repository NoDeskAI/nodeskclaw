import { i18n } from './index'

type ApiErrorData = {
  message?: string
  message_key?: string
  message_params?: Record<string, string>
  error_code?: number
}

function readErrorData(error: unknown): ApiErrorData {
  const data = (error as any)?.response?.data
  if (data && typeof data === 'object') {
    return data as ApiErrorData
  }
  return {}
}

export function resolveApiErrorMessage(error: unknown, fallback = ''): string {
  const { message_key, message, message_params } = readErrorData(error)
  if (message_key && i18n.global.te(message_key)) {
    return i18n.global.t(message_key, message_params ?? {})
  }
  if (message && message.trim()) return message
  if (fallback) return fallback
  if (i18n.global.te('errors.system.internal_error')) {
    return i18n.global.t('errors.system.internal_error')
  }
  return 'Internal server error'
}
