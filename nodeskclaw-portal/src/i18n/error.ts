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

const GENERIC_KEY_PREFIX = 'errors.common.'

export function resolveApiErrorMessage(error: unknown, fallback = ''): string {
  const { message_key, message, message_params } = readErrorData(error)
  const hasSpecificMessage = !!(message && message.trim())
  const isGenericKey = message_key?.startsWith(GENERIC_KEY_PREFIX)

  if (isGenericKey && hasSpecificMessage) {
    return message!.trim()
  }
  if (message_key && i18n.global.te(message_key)) {
    return i18n.global.t(message_key, message_params ?? {})
  }
  if (hasSpecificMessage) return message!.trim()
  if (fallback) return fallback
  if (i18n.global.te('errors.system.internal_error')) {
    return i18n.global.t('errors.system.internal_error')
  }
  return 'Internal server error'
}
