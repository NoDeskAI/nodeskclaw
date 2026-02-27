import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from '@/router'
import { i18n } from '@/i18n'
import App from './App.vue'
import '@/styles/globals.css'

const app = createApp(App)
app.use(createPinia())
app.use(i18n)
app.use(router)
app.mount('#app')
