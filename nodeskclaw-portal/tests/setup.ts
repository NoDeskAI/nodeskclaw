import { vi } from 'vitest'
import { config } from '@vue/test-utils'

vi.mock('@/services/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { code: 0, data: {} } }),
    post: vi.fn().mockResolvedValue({ data: { code: 0, data: {} } }),
    put: vi.fn().mockResolvedValue({ data: { code: 0, data: {} } }),
    delete: vi.fn().mockResolvedValue({ data: { code: 0, data: {} } }),
  },
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
    locale: { value: 'zh-CN' },
  }),
  createI18n: () => ({
    global: { t: (key: string) => key },
    install: vi.fn(),
  }),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    isLoggedIn: true,
    token: 'test-token',
    user: { id: 'u1', name: 'Test User' },
  }),
}))

config.global.stubs = {
  teleport: true,
}
